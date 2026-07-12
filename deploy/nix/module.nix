# tandem hub — NixOS service module (mine.services.tandem-hub).
#
# The hub is a stdlib-only Python process (hub/server.py): ledger + HTTP
# API + the in-process gateway worker for the member whose Macs ride a
# things-gateway write queue instead of running a spoke.
#
# Secrets never live in the nix store: the things-queue bearer token and
# every spoke device token are root-only files materialized out of band at
# deploy time (from a secrets manager) and read via systemd LoadCredential.
# The hub stores only sha256 hashes of device tokens; rotation = rewrite
# the file + restart the service.

{ config, lib, pkgs, src, ... }:

with lib;

let
  cfg = config.mine.services.tandem-hub;

  bootstrapJson = builtins.toJSON {
    tenant = cfg.bootstrap.tenant;
    members = cfg.bootstrap.members;
    devices = map
      (d: {
        member = d.member;
        name = d.name;
        token_credential = d.name + "-token";
      })
      cfg.bootstrap.devices;
  };

  deviceCredentials = map
    (d: "${d.name}-token:${d.tokenFile}")
    cfg.bootstrap.devices;
in
{
  options.mine.services.tandem-hub = {
    enable = mkEnableOption "tandem hub (multi-account Things 3 delegation)";

    port = mkOption {
      type = types.port;
      default = 8712;
      description = "TCP port the hub HTTP API listens on.";
    };

    bindAddress = mkOption {
      type = types.str;
      default = "0.0.0.0";
      description = "Address the HTTP API binds to.";
    };

    bootstrap = {
      tenant = mkOption {
        type = types.str;
        description = "Tenant name, ensured idempotently at startup.";
      };
      members = mkOption {
        type = types.listOf (types.submodule {
          options = {
            handle = mkOption { type = types.str; };
            display_name = mkOption { type = types.str; };
            admin = mkOption { type = types.bool; default = false; };
          };
        });
        default = [ ];
        description = "Members ensured idempotently at startup.";
      };
      devices = mkOption {
        type = types.listOf (types.submodule {
          options = {
            member = mkOption { type = types.str; description = "Member handle."; };
            name = mkOption { type = types.str; description = "Device name."; };
            tokenFile = mkOption {
              type = types.path;
              description = ''
                Root-only file holding this device's bearer token,
                materialized out of band at deploy time. The hub stores
                only its sha256.
              '';
            };
          };
        });
        default = [ ];
        description = "Spoke devices provisioned declaratively.";
      };
    };

    gatewayMember = mkOption {
      type = types.nullOr types.str;
      default = null;
      description = ''
        Member handle whose spoke runs in-process against a things-gateway
        (mirror reads + queue writes) instead of a per-Mac agent.
      '';
    };

    triggerTags = mkOption {
      type = types.attrsOf (types.listOf types.str);
      default = { };
      example = { jill = [ "jill" ]; };
      description = ''
        For the gateway member's outbound scan: recipient handle -> EXACT
        tag titles (case-insensitive, never substring-matched) that trigger
        delegation.
      '';
    };

    mirrorPath = mkOption {
      type = types.path;
      default = "/var/lib/things-mirror/main.sqlite";
      description = "Synced Things DB mirror the gateway member's reads use.";
    };

    queueUrl = mkOption {
      type = types.str;
      default = "http://127.0.0.1:8090";
      description = "things-queue base URL for the gateway member's writes.";
    };

    queueTokenFile = mkOption {
      type = types.path;
      default = "/etc/things-queue-token";
      description = "Root-only file with the things-queue bearer token.";
    };

    tickSeconds = mkOption {
      type = types.int;
      default = 60;
      description = "Gateway worker tick interval.";
    };

    openFirewall = mkOption {
      type = types.bool;
      default = false;
      description = "Open `port` in the firewall (spokes authenticate with bearer tokens).";
    };
  };

  config = mkIf cfg.enable {
    systemd.services.tandem-hub = {
      description = "tandem hub — multi-account Things 3 delegation";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      environment = {
        TANDEM_PORT = toString cfg.port;
        TANDEM_BIND = cfg.bindAddress;
        TANDEM_BOOTSTRAP = bootstrapJson;
        TANDEM_TICK_SECONDS = toString cfg.tickSeconds;
        THINGS_MIRROR_DB = cfg.mirrorPath;
        THINGS_QUEUE_URL = cfg.queueUrl;
      } // optionalAttrs (cfg.gatewayMember != null) {
        TANDEM_GATEWAY_MEMBER = cfg.gatewayMember;
        TANDEM_TRIGGER_TAGS = builtins.toJSON cfg.triggerTags;
      };
      serviceConfig = {
        Type = "simple";
        ExecStart = "${pkgs.python3}/bin/python3 -m hub.server";
        WorkingDirectory = "${src}";
        Restart = "always";
        RestartSec = 5;
        DynamicUser = true;
        StateDirectory = "things-team"; # -> /var/lib/things-team
        LoadCredential = [ "queue-token:${cfg.queueTokenFile}" ]
          ++ deviceCredentials;
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
      };
    };

    networking.firewall.allowedTCPPorts = lib.optional cfg.openFirewall cfg.port;
  };
}

{
  description = "Things Team — multi-account task delegation for Things 3";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system:
        f nixpkgs.legacyPackages.${system});
    in
    {
      # The hub as a NixOS service module: mine.services.things-team-hub
      nixosModules.things-team-hub = { config, lib, pkgs, ... }@args:
        import ./deploy/nix/module.nix (args // { src = self; });
      nixosModules.default = self.nixosModules.things-team-hub;

      checks = forAll (pkgs: {
        tests = pkgs.runCommand "things-team-tests" { } ''
          cd ${self}
          ${pkgs.python3}/bin/python3 -m unittest discover tests
          touch $out
        '';
      });
    };
}

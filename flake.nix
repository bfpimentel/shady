{
  description = "shady dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            uv
          ];

          shellHook = ''
            echo "### SHADY #######################################################"

            if [ -f ".env" ]; then
              source .env
              echo "Loaded .env file"
            else
              echo "You should setup a .env file. Use .env.example as the scaffold."
            fi

            if [ ! -d ".venv" ]; then
              uv venv .venv
            fi

            source .venv/bin/activate
            uv sync

            echo "dev shell ready"
            echo "### SHADY #######################################################"
          '';
        };
      }
    );
}

{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  nativeBuildInputs = with pkgs.buildPackages; [
    ncurses
    openssh
    git
    corepack_24
    nodejs-slim
    uv
  ];

  packages = [
    pkgs.chromium
    (pkgs.python3.withPackages (python-pkgs: [
      python-pkgs.playwright
      python-pkgs.pytest
      python-pkgs.pytest-asyncio
    ]))
  ];

  SLEY_BROWSER_EXECUTABLE = "${pkgs.chromium}/bin/chromium";
}

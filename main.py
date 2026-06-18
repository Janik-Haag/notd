#!/usr/bin/env python3
from collections import defaultdict
from pathlib import Path

import argparse
import os
import re
import sys

import nixeval


def discover_probably_packages(abs_nixpkgs_path: str) -> dict[str, str]:
    def add_package(attr_name: str, file_path: str) -> None:
        probably_packages[attr_name.strip()] = Path(abs_nixpkgs_path, file_path)

    probably_packages = {}
    with open(Path(abs_nixpkgs_path, "pkgs/top-level/all-packages.nix"), "r") as file:
        lines = file.readlines()
        for l in lines:
            # TODO: this should be a ast parser (e.g. rnix)
            # maybe recurseIntoAttrs could be used to detect packageSets e.g. python3Packages
            capture = re.search("(\\b.*)=.*callPackage.*(\\.\\/.*?)( |{|\\))", l)
            if not capture:
                continue
            add_package(capture.group(1), str(Path("pkgs/top-level/../", capture.group(2))))

    abs_pkgs_by_name = Path(abs_nixpkgs_path, "pkgs/by-name/")
    for two_letter_path in os.listdir(abs_pkgs_by_name):
        if not os.path.isdir(Path(abs_pkgs_by_name, two_letter_path)):
            continue

        # TODO: investigate a bunch of questionable eval failures
        # e.g. pkgs/by-name/ki/kikit/package.nix doesn't get 100% correctly identified because the pkg is written badly
        # could probably run the regex again, if there is a callPackage recurisvley resolve and flatten all the attrs
        for package_path in os.listdir(Path(abs_pkgs_by_name, two_letter_path)):
            add_package(package_path, str(Path("pkgs/by-name/", two_letter_path, package_path, "package.nix")))

    return probably_packages


def extract_package_fuction_attrnames(probably_packages: dict[str, str]) -> dict[str, list[str]]:
    evaled_graph = {}
    for attr_name, file_path in probably_packages.items():
        nix_eval_str = f"builtins.attrNames (builtins.functionArgs (import {file_path}))"
        try:
            eval_result = set(nixeval.loads(nix_eval_str))
        except ValueError:
            print(f"couldn't eval {file_path}", file=sys.stderr)
            continue
        evaled_graph[attr_name] = eval_result
    return evaled_graph


def traverse_package_graph(all_targets, evaled_graph) -> list[str]:
    current_targets = all_targets
    inverted_graph = defaultdict(set)

    for attr_name, call_package_args in evaled_graph.items():
        for package in call_package_args:
            inverted_graph[package].add(attr_name)

    while current_targets != set():
        new_targets = set()

        for ct in current_targets:
            new_targets.update(inverted_graph[ct])

        all_targets.update(current_targets)
        current_targets = new_targets - all_targets
    return all_targets


def main() -> None:
    parser = argparse.ArgumentParser(prog="notd", description="nix overlay target determinator")
    parser.add_argument("nixpkgs_path")
    parser.add_argument("overlay_expression")
    args = parser.parse_args()

    abs_nixpkgs_path = os.path.abspath(args.nixpkgs_path)
    all_targets = set(nixeval.loads(args.overlay_expression))

    probably_packages = discover_probably_packages(abs_nixpkgs_path)
    evaled_graph = extract_package_fuction_attrnames(probably_packages)
    print(traverse_package_graph(all_targets, evaled_graph))


if __name__ == "__main__":
    main()

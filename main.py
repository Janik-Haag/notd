#!/usr/bin/env python3
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import argparse
import json
import os
import subprocess
import sys
import tempfile


def eval_nix(nix_expr: str):
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".nix",
        delete=True,
    ) as tf:
        tf.write(nix_expr)
        tf.flush()

        result = subprocess.check_output(
            [
                "nix-instantiate",
                "--eval",
                "--strict",
                "--json",
                tf.name,
            ],
            text=True,
            stderr=subprocess.PIPE,
        )
    return json.loads(result)


def discover_toplevel_packages(abs_nixpkgs_path: str) -> dict[str, Path]:
    nix_eval_str = f"""
    with import {abs_nixpkgs_path} {{ }};
        builtins.mapAttrs (n: v:
        let
            try = builtins.tryEval (v.meta or "no_meta").position or "${{n}} doesn't have meta or position attr";
        in if try.success then
            try.value
        else "failed to evaluate ${{n}}"
    ) pkgs
    """
    eval_result: dict[str, str] = eval_nix(nix_eval_str)
    result: dict[str, Path] = {}
    for attr_name, file_path in eval_result.items():
        if file_path.startswith("/nix/store/"):
            # path looks like `/etc/nixos/nixpkgs/pkgs/by-name/aa/aaa/package.nix:21`
            file_path_without_line_num = "".join(file_path.split(":")[:-1])
            non_nixstored_slice = Path(file_path_without_line_num).parts[4:]
            result[attr_name] = Path(abs_nixpkgs_path, *non_nixstored_slice)
        else:
            # already holds a error val, was set during eval
            print(file_path, file=sys.stderr)

    return result


def eval_package(item):
    attr_name, file_path = item

    nix_eval_str = f"builtins.attrNames (builtins.functionArgs (import {file_path}))"

    try:
        eval_result = set(eval_nix(nix_eval_str))
        return attr_name, eval_result
    except subprocess.CalledProcessError:
        print(f"couldn't eval {file_path}", file=sys.stderr)
        return attr_name, None


def extract_package_fuction_attrnames(probably_packages: dict[str, Path]) -> dict[str, set[str]]:
    evaled_graph = {}

    with ProcessPoolExecutor(max_workers=os.cpu_count()) as pool:
        futures = [pool.submit(eval_package, item) for item in probably_packages.items()]

        for future in as_completed(futures):
            attr_name, result = future.result()

            if result:
                evaled_graph[attr_name] = result

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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    abs_nixpkgs_path = os.path.abspath(args.nixpkgs_path)
    all_targets = set(eval_nix(args.overlay_expression))

    toplevel_packages = discover_toplevel_packages(abs_nixpkgs_path)
    evaled_graph = extract_package_fuction_attrnames(toplevel_packages)

    targets = traverse_package_graph(all_targets, evaled_graph)
    if args.json:
        # hack, json can't deseralize sets...
        print(json.dumps(targets, default=list))
    else:
        print(targets)


if __name__ == "__main__":
    main()

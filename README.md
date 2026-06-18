# NOTD - Nix Overlay Target Determinator

Let's say you have a nixpkgs overlay, and now you want to have caching, so you need to rebuild all the things effected by the overlay(s).
You could do what hydra is doing, and just eval every `pkgs.*` attribute, but that expensive, it eats a ton of ram, and takes for ever.

This little program looks for package declarations at some known places, mostly `pkgs/by-name`, and `pkgs/top-level/all-packages.nix`.
It does this using some cursed heuristics, like a regex matching for callPackage.
Once it figured out where the packages are declared, it uses `builtins.attrNames (builtins.functionArgs (import $package_file))`.
In nixpkgs you need to declare all the attrs you depend on, e.g. you can't just access pkgs.foo, this means that every dependent should be in the functionArgs.

Now that we have a list of `{ pkgs.$name = [ pkgs.foo pkgs.bar ]; }`, we can invert them, e.g. `{ pkgs.foo = [ pkgs.$name ]; pkgs.bar = [ pkgs.$name ]; }`.
This makes querying very cheap. So now we just need a list of packages changed by our overlay, then we look it up in the inverted set,
and we repeat the process, until we have a full list of packages affected.

This python code did the above described procedure in consitently less then 5 seconds on my laptop, even with packages such as gcc, and xz.
Currently this only supports the default package set, but in theory there is nothing preventing this approach from being adopted to other package sets.

Try it!
```bash
export PATH_TO_LOCAL_NIXPKGS=$(nix-instantiate --eval -E 'with import <nixpkgs> { }; pkgs.path')
export EXPR_TO_EVAL_OVERLAY="builtins.attrNames (import ./example_overlay.nix {} {})"
nix-shell -p uv --run 'uv run notd "$PATH_TO_LOCAL_NIXPKGS" "$EXPR_TO_EVAL_OVERLAY"' 2>/dev/null
```

__IMPORTANT:__ this is a heuristc, it isn't a 100% accurate.

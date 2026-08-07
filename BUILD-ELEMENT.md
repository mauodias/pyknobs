# Building Element 1.1.1 from source

Element 1.1.x installers are supporter-only until 1.2 tags. pyknobs' host-feedback
path needs 1.1.x, so this documents building it locally.

**Result: it built and runs.** `dist/Element-1.1.1.app` (gitignored, 23 MB,
arm64). Drag it wherever you like — it was *not* installed to `/Applications`,
and your existing 1.0.0 is untouched.

## Nothing was installed system-wide

`cmake`, `ninja` and Boost were all fetched into a scratch directory rather than
via Homebrew, so `/opt/homebrew` and the rest of the system are unchanged.

| Need | How |
| --- | --- |
| CMake 3.31.6 | official macOS universal tarball, extracted locally |
| Ninja 1.12.1 | GitHub release zip, extracted locally |
| Boost 1.86.0 | source tarball, **headers only** (`tar xzf … boost_1_86_0/boost`) |
| JUCE 8.0.13 | fetched by CMake `FetchContent` at configure time |
| sol2 | same |
| clap-juce-extensions | git submodule |

Boost is only needed for `boost/signals2` and `boost/algorithm/string` — both
header-only, so no compiled Boost libraries are required.

## The commands

```sh
git clone --depth 1 --branch 1.1.1 --recurse-submodules --shallow-submodules \
    https://github.com/kushview/element.git

cmake -B build -G Ninja \
    -DCMAKE_MAKE_PROGRAM=/path/to/ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DBOOST_INCLUDEDIR=/path/to/boost_1_86_0 \
    -DBoost_INCLUDE_DIR=/path/to/boost_1_86_0 \
    -DELEMENT_BUILD_TESTS=OFF -DELEMENT_BUILD_PLUGINS=OFF

ninja -C build
# -> build/element_app_artefacts/Release/Element.app
```

Build took about 4 minutes on 8 cores: 315 targets, **zero errors or warnings
that stopped the link**.

## Two gotchas

**The source tarball is not enough.** GitHub tarballs omit submodules, so
`deps/clap-juce-extensions` arrives empty and the configure fails. Clone with
`--recurse-submodules` instead.

**CMake may pick the wrong `make`.** On this machine it found
`~/cosmo/make` (a Cosmopolitan build) which died with `Unknown system error -8`
on the compiler probe, making it look like the *compiler* was broken. Using
Ninja sidesteps it; `-DCMAKE_MAKE_PROGRAM=/usr/bin/make` would too.

## What still needs checking by hand

The build is verified — it launches and stays running, reports version `1.1.1`,
and `midicc.lua` is embedded in the binary.

What is **not** verified is the thing that motivated the build: whether a plugin
parameter can drive a Script node's `Knob N` control input. That needs the GUI.

What the source shows: `PerformanceParameter` grew from 6 references and a stub
to 34 references and ~290 lines in 1.1.1, gaining `bindToNode(node, param)` —
matching the changelog line *"Performance parameter connectivity to Script node
parameters"*. So the mechanism is a **performance parameter** binding to a node
parameter, not necessarily a direct plugin-parameter-to-script connection.

The wiring may therefore be:

```
plugin parameter → performance parameter → Script "Knob N" → MIDI out → pyknobs
```

rather than connecting the plugin's parameter port straight to the script. Worth
trying the direct connection first, then the performance-parameter route.

In 1.0.0 the plugin node exposed **2106 control ports, all inputs, zero
outputs** — which is why nothing could drive the script there.

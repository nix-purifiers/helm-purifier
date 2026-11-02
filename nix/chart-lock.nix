# SPDX-License-Identifier: MIT
# Parse the flat YAML schema Helm itself emits for Chart.lock, without IFD.
# JSON (also valid YAML) is accepted. Unsupported YAML constructs fail closed.
{ lib }:
path:
let
  advice = "helm-purifier: cannot parse Chart.lock ${toString path}; run helm-purifier lock to regenerate a native Helm lock";
  text = builtins.readFile path;
  trim = lib.strings.trim;
  scalar =
    raw:
    let
      s = trim raw;
    in
    if lib.hasPrefix "\"" s then
      builtins.addErrorContext advice (builtins.fromJSON s)
    else if lib.hasPrefix "'" s && lib.hasSuffix "'" s then
      lib.replaceStrings [ "''" ] [ "'" ] (builtins.substring 1 (builtins.stringLength s - 2) s)
    else if builtins.match "[A-Za-z0-9][A-Za-z0-9_.+:/@%=-]*" s != null then
      s
    else
      throw advice;
  parseField =
    line:
    let
      match = builtins.match "([A-Za-z][A-Za-z0-9-]*):[ ]*(.*)" line;
    in
    if match == null then
      throw advice
    else
      {
        name = builtins.head match;
        value = scalar (builtins.elemAt match 1);
      };
  lines = lib.filter (
    line:
    let
      s = trim line;
    in
    s != "" && !(lib.hasPrefix "#" s) && s != "---"
  ) (lib.splitString "\n" text);
  finish = state: state.dependencies ++ lib.optional (state.current != null) state.current;
  state =
    builtins.foldl'
      (
        state: line:
        let
          s = trim line;
          newItem = lib.hasPrefix "- " s;
          field = parseField (if newItem then lib.removePrefix "- " s else s);
          top = !(lib.hasPrefix " " line) && !newItem;
          set =
            attrs:
            if builtins.hasAttr field.name attrs then
              throw advice
            else
              attrs // { ${field.name} = field.value; };
        in
        if s == "dependencies:" || s == "dependencies: []" then
          if state.started then throw advice else state // { started = true; }
        else if top then
          if
            !(builtins.elem field.name [
              "digest"
              "generated"
            ])
          then
            throw advice
          else
            state
        else if newItem then
          if !state.started || field.name != "name" then
            throw advice
          else
            state
            // {
              dependencies = finish state;
              current = set { };
            }
        else if
          state.current == null
          || !(builtins.elem field.name [
            "name"
            "version"
            "repository"
          ])
        then
          throw advice
        else
          state // { current = set state.current; }
      )
      {
        dependencies = [ ];
        current = null;
        started = false;
      }
      lines;
in
if lib.hasPrefix "{" (trim text) then
  builtins.addErrorContext advice (builtins.fromJSON text)
else if !state.started then
  throw advice
else
  { dependencies = finish state; }

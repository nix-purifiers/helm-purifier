# SPDX-License-Identifier: MIT
{
  runCommand,
  fetchChart,
  purifier,
}:
{
  lock,
  fetchers ? { },
}:
purifier.tree (
  {
    name = "helm-charts";
    entries = (purifier.checkLock lock).entries;
    inherit runCommand;
    fetchurl = fetchChart;
  }
  // fetchers
)

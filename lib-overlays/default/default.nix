final: prev: {
  helm-purifier = {
    readLock = import ./read-lock.nix { lib = final; };
  };
}

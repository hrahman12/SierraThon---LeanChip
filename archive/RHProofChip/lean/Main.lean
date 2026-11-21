import RHProofChip.Examples
open RHPC

/-- `rhpc-lean emit <dir>`      write the example certificates as binary files
    `rhpc-lean check <files>…`  print the reference verdict for each certificate -/
def main (args : List String) : IO UInt32 := do
  match args with
  | "emit" :: dir :: _ =>
    let certs : List (String × Cert) := [
      ("identity", Examples.identity), ("two_plus_two", Examples.twoPlusTwo),
      ("two_times_two", Examples.twoTimesTwo)]
    for (name, c) in certs do
      IO.FS.writeBinFile s!"{dir}/{name}.rhpc" (ByteArray.mk c.encode.toArray)
      IO.println s!"{name}.rhpc {c.encode.length} bytes, {c.steps.length} steps"
    return 0
  | "check" :: files =>
    for f in files do
      let bs ← IO.FS.readBinFile f
      let v := match verdict bs.toList with
        | .accept => "ACCEPT"
        | .rejectMalformed => "REJECT_MALFORMED"
        | .rejectInvalid => "REJECT_INVALID"
      IO.println s!"{f}\t{v}"
    return 0
  | _ =>
    IO.eprintln "usage: rhpc-lean emit <dir> | rhpc-lean check <file>..."
    return 2

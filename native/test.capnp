@0xe8a8f7ed434e11b8;
struct Root {
  signed @0 :Int64 = -17;
  unsigned @1 :UInt64 = 42;
  truth @2 :Bool = true;
  fraction @3 :Float64 = -1.25;
  mode @4 :Mode = second;
  child @5 :Child;
  children @6 :List(Child);
  floats @7 :List(Float32);
  modes @8 :List(Mode);
  nested @9 :List(List(UInt16));
  text @10 :Text;
  data @11 :Data;
  group :group {
    value @12 :Int32 = 7;
    nested :group { text @20 :Text; }
  }
  union {
    nothing @13 :Void;
    number @14 :Int32;
    object @15 :Child;
    grouped :group {
      value @17 :Int32 = 11;
      text @18 :Text;
      child @19 :Child;
    }
  }
  link @16 :Root;
  struct Child {
    value @0 :Float64;
    text @1 :Text;
  }
  enum Mode { first @0; second @1; }
}
# An unrelated Event prevents implicit selection by a display-name substring.
struct Event { unrelated @0 :UInt32; }

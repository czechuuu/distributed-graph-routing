from google.protobuf.internal import decoder

def debug_hex(hex_str):
    print(f"Analyzing Hex: {hex_str}")
    data = bytes.fromhex(hex_str)
    
    # Read the first tag
    tag, pos = decoder._DecodeVarint(data, 0)
    
    field_number = tag >> 3
    wire_type = tag & 7
    
    print(f"--- Detected Tag ---")
    print(f"Value: {tag} (0x{tag:02x})")
    print(f"Field Number: {field_number}")
    print(f"Wire Type: {wire_type} ({get_wire_type_name(wire_type)})")
    
    print(f"\n--- Expected for 'fixed64' (Field 1) ---")
    expected_tag = (1 << 3) | 1
    print(f"Expected Tag: {expected_tag} (0x{expected_tag:02x})")
    print(f"Expected Wire Type: 1 (64-bit)")
    
    if tag != expected_tag:
        print(f"\n[MISMATCH] The data has wire type {wire_type}, but fixed64 requires wire type 1.")

def get_wire_type_name(wt):
    if wt == 0: return "Varint"
    if wt == 1: return "64-bit"
    if wt == 2: return "Length-delimited"
    if wt == 5: return "32-bit"
    return "Unknown"

if __name__ == "__main__":
    # The hex we found in Bigtable
    debug_hex("088080808080fe82d547")

#!/usr/bin/env python3
"""
Convert mppdp5 pose JSONL to PoseRendererP5 format.

Input:  work/pose.jsonl (from mppdp5 PoseAdapter)
Output: data/poses-0001.jsonl (for PoseRendererP5)

Format expected by PoseRendererP5:
{
  "t_frame": 0,
  "nodes": [
    {"id": 0, "x": 0.5, "y": 0.3, "z": 0.0, "v": 0.9},
    ...
  ]
}
"""

import json
import sys
from pathlib import Path

# MediaPipe pose landmark names (33)
LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]

def convert(input_path: str, output_path: str):
    input_file = Path(input_path)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        
        frame_idx = 0
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            # mppdp5 PoseAdapter output format
            landmarks = data.get('landmarks', [])
            if not landmarks or len(landmarks) != 132:  # 33 * 4
                continue
            
            nodes = []
            for i in range(33):
                base = i * 4
                x, y, z, v = landmarks[base:base+4]
                if v > 0.3:  # visibility threshold
                    nodes.append({
                        "id": i,
                        "x": x,
                        "y": y,
                        "z": z,
                        "v": v
                    })
            
            if nodes:
                out = {
                    "t_frame": frame_idx,
                    "nodes": nodes
                }
                f_out.write(json.dumps(out, ensure_ascii=False) + "\n")
            
            frame_idx += 1
    
    print(f"Converted {frame_idx} frames -> {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python convert_pose.py <input.jsonl> <output.jsonl>")
        print("Example: python convert_pose.py work/pose.jsonl demos/processing-renderer/PoseRendererP5/data/poses-0001.jsonl")
        sys.exit(1)
    
    convert(sys.argv[1], sys.argv[2])
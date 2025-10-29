#!/usr/bin/env python3
"""
Process JSON annotations to add text property to parent annotations
by concatenating words from their children.
"""

import json
import os
from typing import Dict, List, Any


def simplify_annotations_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simplify annotations in-memory: concatenate word children into a parent "text"
    field (sorted by reading order), remove child relationships, and drop child
    annotations entirely. Returns the simplified data dict (modified in place).
    """
    # Create a mapping of annotation IDs to annotations for quick lookup
    annotation_map: Dict[str, Dict[str, Any]] = {
        ann["_annotation_id"]: ann for ann in data.get("annotations", [])
    }

    processed_count = 0
    child_ids_to_remove = set()

    for annotation in data.get("annotations", []):
        relationships = annotation.get("relationships", {})
        if "child" in relationships:
            child_ids = relationships["child"]
            child_ids_to_remove.update(child_ids)

            word_data: List[Dict[str, Any]] = []
            for child_id in child_ids:
                child = annotation_map.get(child_id)
                if not child:
                    continue
                if child.get("category_name") == "word":
                    text_value = extract_word_text(child)
                    reading_order = extract_reading_order(child)
                    if text_value:
                        word_data.append({
                            "text": text_value,
                            "reading_order": reading_order
                        })

            if word_data:
                word_data.sort(key=lambda x: x["reading_order"])
                annotation["text"] = " ".join(w["text"] for w in word_data)

                # Remove the child relationships after extracting text
                relationships.pop("child", None)
                if not relationships:
                    annotation.pop("relationships", None)
                else:
                    annotation["relationships"] = relationships
                processed_count += 1

    # Remove child annotations that are no longer needed
    if child_ids_to_remove:
        data["annotations"] = [
            ann for ann in data.get("annotations", [])
            if ann.get("_annotation_id") not in child_ids_to_remove
        ]

    # Order remaining parent annotations in reading order
    def get_page_bbox(d: Dict[str, Any]) -> Dict[str, Any]:
        bbox = d.get("_bbox") or {}
        # Fallback to a default size if missing
        return {
            "ulx": bbox.get("ulx", 0),
            "uly": bbox.get("uly", 0),
            "lrx": bbox.get("lrx", 1000),
            "lry": bbox.get("lry", 1000),
        }

    def to_absolute_bbox(bbox: Dict[str, Any], page_bbox: Dict[str, Any]) -> Dict[str, int]:
        page_w = max(1, int(page_bbox["lrx"] - page_bbox["ulx"]))
        page_h = max(1, int(page_bbox["lry"] - page_bbox["uly"]))
        if bbox.get("absolute_coords", True):
            return {
                "ulx": int(bbox.get("ulx", 0)),
                "uly": int(bbox.get("uly", 0)),
                "lrx": int(bbox.get("lrx", 0)),
                "lry": int(bbox.get("lry", 0)),
            }
        # normalized → scale to pixels
        return {
            "ulx": int(float(bbox.get("ulx", 0)) * page_w),
            "uly": int(float(bbox.get("uly", 0)) * page_h),
            "lrx": int(float(bbox.get("lrx", 0)) * page_w),
            "lry": int(float(bbox.get("lry", 0)) * page_h),
        }

    def order_parents(parents: List[Dict[str, Any]], page_bbox: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Build items with absolute positions
        items = []
        for ann in parents:
            bbox = ann.get("bounding_box") or {}
            absb = to_absolute_bbox(bbox, page_bbox)
            x_center = (absb["ulx"] + absb["lrx"]) / 2.0
            y_top = absb["uly"]
            items.append({
                "ann": ann,
                "abs": absb,
                "cx": x_center,
                "yt": y_top,
            })

        # Simple column clustering by x center with adaptive threshold
        page_w = max(1, int(page_bbox["lrx"] - page_bbox["ulx"]))
        column_threshold = max(int(0.08 * page_w), 60)  # 8% of width or 60px

        items.sort(key=lambda x: x["cx"])  # sort by x to form columns L→R
        columns: List[Dict[str, Any]] = []
        for it in items:
            placed = False
            for col in columns:
                if abs(it["cx"] - col["center"]) <= column_threshold:
                    col["members"].append(it)
                    # update running center
                    col["center"] = sum(m["cx"] for m in col["members"]) / len(col["members"]) 
                    placed = True
                    break
            if not placed:
                columns.append({"center": it["cx"], "members": [it]})

        # Order columns by x, and within each column top→bottom then left→right
        columns.sort(key=lambda c: c["center"])  # left→right columns
        ordered: List[Dict[str, Any]] = []
        for col in columns:
            col["members"].sort(key=lambda m: (m["yt"], m["abs"]["ulx"]))
            ordered.extend(m["ann"] for m in col["members"])

        return ordered

    page_bbox = get_page_bbox(data)
    data["annotations"] = order_parents(data.get("annotations", []), page_bbox)

    return data


async def process_annotations(input_file: str, output_file: str = None) -> None:
    """
    Process JSON annotations to add text property to parent annotations.
    
    Args:
        input_file: Path to input JSON file
        output_file: Path to output JSON file (optional, defaults to input_file with _processed suffix)
    """
    if output_file is None:
        base_name = os.path.splitext(input_file)[0]
        output_file = f"{base_name}_processed.json"
    
    print(f"Reading annotations from: {input_file}")
    
    # Read the JSON file
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Simplify in-memory and report minimal stats
    before_count = len(data.get('annotations', []))
    simplify_annotations_data(data)
    after_count = len(data.get('annotations', []))
    print(f"Simplified annotations: {before_count} -> {after_count}")
    
    # Save the processed data
    print(f"Saving processed annotations to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print("Processing complete!")


def extract_word_text(word_annotation: Dict[str, Any]) -> str:
    """
    Extract text value from a word annotation.
    
    Args:
        word_annotation: The word annotation dictionary
        
    Returns:
        The text value if found, empty string otherwise
    """
    # Look for text in sub_categories
    if 'sub_categories' in word_annotation:
        for sub_cat_name, sub_cat_data in word_annotation['sub_categories'].items():
            if isinstance(sub_cat_data, dict) and 'value' in sub_cat_data:
                return sub_cat_data['value']
    
    # Look for text in the main annotation
    if 'value' in word_annotation:
        return word_annotation['value']
    
    return ""


def extract_reading_order(word_annotation: Dict[str, Any]) -> int:
    """
    Extract reading order from a word annotation.
    
    Args:
        word_annotation: The word annotation dictionary
        
    Returns:
        The reading order value if found, 999999 otherwise (to put unordered items at end)
    """
    # Look for reading_order in sub_categories
    if 'sub_categories' in word_annotation:
        reading_order_data = word_annotation['sub_categories'].get('reading_order')
        if isinstance(reading_order_data, dict) and 'category_id' in reading_order_data:
            return reading_order_data['category_id']
    
    # If no reading order found, return a large number to put it at the end
    return 999999


async def main():
    """Main function to process annotations."""
    # Get the output directory
    output_dir = "/home/matt/Desktop/Projects/deepdoctection/output"
    
    # Find all JSON files in the output directory
    json_files = [f for f in os.listdir(output_dir) if f.endswith('.json')]
    
    if not json_files:
        print("No JSON files found in the output directory")
        return
    
    print(f"Found {len(json_files)} JSON file(s) to process:")
    for file in json_files:
        print(f"  - {file}")
    
    # Process each JSON file
    for json_file in json_files:
        input_path = os.path.join(output_dir, json_file)
        await process_annotations(input_path)
        print("-" * 50)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

DeepDoctection API + Annotation Simplifier

Overview
- FastAPI service that parses document images using DeepDoctection
- Post-processing that simplifies page annotations for easier consumption
  - Concatenates child word annotations into a parent `text`
  - Removes `relationships.child` and child annotations entirely
  - Orders remaining annotations in page reading order: columns left→right; within each column top→bottom

Project layout
- `api.py` — FastAPI server exposing `/parse` and `/health`
- `process_annotations.py` — in-memory simplifier (`simplify_annotations_data`) and a CLI to batch-process JSON in `output/`
- `requirements.txt` — Python dependencies

Prerequisites
- Python 3.10+ recommended
- pip

Setup
```bash
cd /home/matt/Desktop/Projects/deepdoctection
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the API
```bash
# from the project root
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Health check
```bash
curl http://127.0.0.1:8000/health
```
Expected response:
```json
{"status": "healthy"}
```

Parse an image
The `/parse` endpoint requires a multipart form field named `file` with an image.

curl
```bash
curl -F "file=@/home/matt/Desktop/Projects/deepdoctection/2025-10-29_11-40.png" \
  http://127.0.0.1:8000/parse
```

Python (requests)
```python
import requests

url = 'http://127.0.0.1:8000/parse'
with open('/home/matt/Desktop/Projects/deepdoctection/2025-10-29_11-40.png', 'rb') as f:
    res = requests.post(url, files={'file': ('2025-10-29_11-40.png', f, 'image/png')})
print(res.status_code)
print(res.json())
```

Response shape
```json
{
  "success": true,
  "pages": [
    {
      "file_name": "...",
      "_bbox": {"ulx": 0, "uly": 0, "lrx": W, "lry": H},
      "annotations": [
        {
          "_annotation_id": "...",
          "category_name": "text" | "figure" | "list" | ...,
          "bounding_box": {"absolute_coords": true, "ulx": X1, "uly": Y1, "lrx": X2, "lry": Y2},
          "text": "concatenated words in reading order"
        }
      ]
    }
  ],
  "total_pages": 1
}
```

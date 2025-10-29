import json
import tempfile
import os
from pathlib import Path
from typing import Dict, Any
import uuid

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from process_annotations import simplify_annotations_data
import deepdoctection as dd

app = FastAPI(title="Document Parser API", version="1.0.0")

# Ensure output directory exists
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

@app.post("/parse")
async def parse_document(file: UploadFile = File(...)) -> JSONResponse:
    """
    Parse an uploaded image document and return the extracted JSON data.
    The temporary files are automatically cleaned up after processing.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Create temporary file for the uploaded image
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
        try:
            # Write uploaded file to temporary location
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            
            # Initialize analyzer
            analyzer = dd.get_dd_analyzer()
            
            # Process the image
            df = analyzer.analyze(path=temp_file.name, bytes=content)
            df.reset_state()
            
            # Collect all page records
            all_pages_records = []
            temp_json_files = []
            
            for idx, page in enumerate(df, start=1):
                # Generate unique filename for this page
                page_id = str(uuid.uuid4())
                out_path = output_dir / f"{page_id}_p{idx}.json"
                
                # Save page data
                page.save(
                    image_to_json=False,
                    highest_hierarchy_only=False,
                    path=str(out_path)
                )
                
                # Read the saved JSON, simplify annotations, and add to results
                with open(out_path, 'r') as f:
                    page_data = json.load(f)
                    simplified = simplify_annotations_data(page_data)
                    all_pages_records.append(simplified)
                
                # Track for cleanup
                temp_json_files.append(out_path)
            
            # Clean up temporary JSON files
            for json_file in temp_json_files:
                try:
                    os.unlink(json_file)
                except OSError:
                    pass  # File might already be deleted
            
            # Return the parsed data
            return JSONResponse(content={
                "success": True,
                "pages": all_pages_records,
                "total_pages": len(all_pages_records)
            })
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")
        
        finally:
            # Clean up temporary image file
            try:
                os.unlink(temp_file.name)
            except OSError:
                pass  # File might already be deleted

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

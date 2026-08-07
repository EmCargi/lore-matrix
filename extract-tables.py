#!/usr/bin/env python3
"""
Lore Matrix - Tabular Data Extractor (Hardened & Strict)
Ingests PDFs, extracts structured floating-point tabular data (like lab reports) 
using pdfplumber, and outputs them as sanitized CSV files.
"""

import csv
import glob
import os
import shutil

import pdfplumber

# Directory constants matching the pipeline
INPUT_PDFS_DIR = "input_pdfs"
PROCESSED_PDFS_DIR = "processed_pdfs"
OUTPUT_CSVS_DIR = "processed_data"

def extract_and_save_tables(pdf_file_path):
    """
    Extracts tabular data from the first page of the PDF and saves it to a CSV file.
    """
    print(f"🔥 Starting table extraction for: {pdf_file_path}")
    
    base_name = os.path.basename(pdf_file_path)
    csv_name = os.path.splitext(base_name)[0] + ".csv"
    csv_path = os.path.join(OUTPUT_CSVS_DIR, csv_name)
    
    with pdfplumber.open(pdf_file_path) as pdf:
        if not pdf.pages:
            raise ValueError("The PDF document has no pages! Absolutely useless!")
        
        # Target the first page
        first_page = pdf.pages[0]
        
        # Extract tables
        tables = first_page.extract_tables()
        if not tables:
            print("⚠️ No tables found on the first page. It's raw!")
            return
        
        cleaned_rows = []
        for table in tables:
            for row in table:
                # Clean row: replace inline \n with spaces, convert None to empty string
                cleaned_row = []
                for cell in row:
                    val = str(cell) if cell is not None else ""
                    val = val.replace("\n", " ")
                    cleaned_row.append(val)
                
                # Ignore completely empty rows (checking if any cell has non-whitespace characters)
                if any(cell.strip() for cell in cleaned_row):
                    cleaned_rows.append(cleaned_row)
        
        if not cleaned_rows:
            print("⚠️ The extracted table contains no content. Empty plate!")
            return
            
        print(f"🍳 Extracted {len(cleaned_rows)} cleaned rows. Writing to CSV...")
        
        # Save to CSV
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(cleaned_rows)
            
        print(f"📝 SUCCESS: Saved tables to {csv_path}")


def main():
    # Ensure directories are created dynamically on runtime
    os.makedirs(INPUT_PDFS_DIR, exist_ok=True)
    os.makedirs(PROCESSED_PDFS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_CSVS_DIR, exist_ok=True)
    
    # Sweep INPUT_PDFS_DIR for any .pdf files using glob
    target_pdfs = glob.glob(os.path.join(INPUT_PDFS_DIR, "*.pdf"))
    
    if not target_pdfs:
        print(f"📭 The hopper is empty! No PDFs found in {INPUT_PDFS_DIR}/")
        return
        
    print(f"☕ Found {len(target_pdfs)} PDFs in the hopper. Let's get to work!")
    
    for pdf_file in target_pdfs:
        print("\n======================================")
        print(f"🎯 Target Acquired: {pdf_file}")
        print("======================================")
        
        try:
            extract_and_save_tables(pdf_file)
            
            # Archive raw PDF into PROCESSED_PDFS_DIR
            filename = os.path.basename(pdf_file)
            destination = os.path.join(PROCESSED_PDFS_DIR, filename)
            shutil.move(pdf_file, destination)
            print(f"📦 Archived: {filename} moved to {PROCESSED_PDFS_DIR}/")
            
        except Exception as e:
            print(f"❌ CRITICAL FAILURE on {pdf_file}: {e}")
            print("⚠️ Leaving file in the input hopper so you can sort out your mess!")


if __name__ == "__main__":
    main()

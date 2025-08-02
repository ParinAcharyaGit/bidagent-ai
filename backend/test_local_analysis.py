#!/usr/bin/env python3

import sys
import os

# Add the current directory to path so we can import from agents
sys.path.insert(0, '.')

from agents.document_processing_agent.tools import extract_fields_with_local_heuristics

def test_local_analysis():
    # Test with a known PDF
    pdf_path = "/Users/darwinvargas/Documents/Business/Techforcement/bidagent-ai/docs/Bid 25-20, General and Athletic Landscaping Services.pdf"
    
    print("=" * 60)
    print("TESTING LOCAL HEURISTICS ANALYSIS WITH TIMING LOGS")
    print("=" * 60)
    print(f"Testing with PDF: {pdf_path}")
    print()
    
    try:
        result = extract_fields_with_local_heuristics(pdf_path)
        print("\n" + "=" * 60)
        print("ANALYSIS COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print("Result preview:")
        if len(result) > 500:
            print(result[:500] + "... (truncated)")
        else:
            print(result)
    except Exception as e:
        print("\n" + "=" * 60)
        print("ANALYSIS FAILED")
        print("=" * 60)
        print(f"Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_local_analysis()

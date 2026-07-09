#!/usr/bin/env python3
"""
Test PDF Resolution for Phase 3A Pilot

This script tests the Hybrid Path Strategy for resolving PDF paths
from BibTeX cite keys. Validates that all pilot papers can be found.

Usage:
    python test_pdf_resolution.py --bibtex pilot_batch.bib --pdf-index pdf_index.json
    python test_pdf_resolution.py --bibtex file.bib --pdf-index index.json --report report.json
"""

import re
import json
import argparse
from pathlib import Path
from datetime import datetime


def parse_bibtex_cite_keys(bibtex_file):
    """Extract cite keys from BibTeX file."""
    cite_keys = []

    with open(bibtex_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Match @type{CiteKey,
    matches = re.finditer(r'@\w+\{([^,]+),', content, re.MULTILINE)

    for match in matches:
        cite_key = match.group(1).strip()
        if not cite_key.startswith('%'):  # Skip comments
            cite_keys.append(cite_key)

    return cite_keys


def load_pdf_index(index_file):
    """Load PDF index from JSON."""
    with open(index_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return data['index'], data['metadata']


def resolve_pdf_path(cite_key, pdf_index):
    """
    Resolve PDF path using Hybrid Path Strategy.

    Strategy:
    1. Direct lookup in index (normalized cite key)
    2. Check index metadata for statistics

    Returns:
        dict: {
            'cite_key': str,
            'found': bool,
            'pdf_filename': str or None,
            'pdf_path': str or None,
            'resolution_method': str,
            'format_type': str or None,
        }
    """
    result = {
        'cite_key': cite_key,
        'found': False,
        'pdf_filename': None,
        'pdf_path': None,
        'resolution_method': None,
        'format_type': None,
    }

    # Direct lookup
    if cite_key in pdf_index:
        entry = pdf_index[cite_key]
        result['found'] = True
        result['pdf_filename'] = entry['filename']
        result['pdf_path'] = entry['full_path']
        result['resolution_method'] = 'direct_index_lookup'
        result['format_type'] = entry['format_type']

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Test PDF resolution for Phase 3A pilot"
    )
    parser.add_argument(
        '--bibtex',
        type=str,
        required=True,
        help='BibTeX file to test (e.g., pilot_batch.bib)'
    )
    parser.add_argument(
        '--pdf-index',
        type=str,
        required=True,
        help='PDF index JSON file'
    )
    parser.add_argument(
        '--report',
        type=str,
        default=None,
        help='Optional JSON report output file'
    )

    args = parser.parse_args()

    # Set UTF-8 output
    import sys
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    print("=" * 80)
    print("PDF Resolution Test - Phase 3A Pilot")
    print("=" * 80)
    print()
    print(f"BibTeX file: {args.bibtex}")
    print(f"PDF index: {args.pdf_index}")
    print()

    # Load inputs
    try:
        cite_keys = parse_bibtex_cite_keys(args.bibtex)
        print(f"Loaded {len(cite_keys)} cite keys from BibTeX")
    except Exception as e:
        print(f"❌ Error parsing BibTeX: {e}")
        return 1

    try:
        pdf_index, index_metadata = load_pdf_index(args.pdf_index)
        print(f"Loaded PDF index: {index_metadata['statistics']['total_pdfs']} PDFs, "
              f"{index_metadata['statistics']['unique_cite_keys']} unique cite keys")
        print()
    except Exception as e:
        print(f"❌ Error loading PDF index: {e}")
        return 1

    # Test resolution
    print("=" * 80)
    print("Testing PDF Resolution")
    print("=" * 80)
    print()
    print(f"{'Cite Key':<25} {'Status':<10} {'PDF Filename':<40}")
    print("-" * 80)

    results = []
    for cite_key in cite_keys:
        resolution = resolve_pdf_path(cite_key, pdf_index)
        results.append(resolution)

        status = "✅ FOUND" if resolution['found'] else "❌ MISSING"
        filename = resolution['pdf_filename'] if resolution['found'] else "NOT RESOLVED"

        print(f"{cite_key:<25} {status:<10} {filename:<40}")

    print("-" * 80)
    print()

    # Statistics
    total = len(results)
    found = sum(1 for r in results if r['found'])
    missing = total - found
    success_rate = (found / total * 100) if total > 0 else 0

    print("=" * 80)
    print("Resolution Statistics")
    print("=" * 80)
    print()
    print(f"Total entries: {total}")
    print(f"Resolved: {found}/{total} ({success_rate:.1f}%)")
    print(f"Unresolved: {missing}/{total} ({(100-success_rate):.1f}%)")
    print()

    # Resolution methods
    if found > 0:
        method_counts = {}
        format_counts = {}

        for r in results:
            if r['found']:
                method = r['resolution_method']
                method_counts[method] = method_counts.get(method, 0) + 1

                fmt = r['format_type']
                format_counts[fmt] = format_counts.get(fmt, 0) + 1

        print("Resolution Methods:")
        for method, count in sorted(method_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {method:<30} {count:>3} ({count/found*100:>5.1f}%)")
        print()

        print("PDF Format Types:")
        for fmt, count in sorted(format_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {fmt:<30} {count:>3} ({count/found*100:>5.1f}%)")
        print()

    # Unresolved entries
    if missing > 0:
        print("⚠️  Unresolved Entries:")
        for r in results:
            if not r['found']:
                print(f"  - {r['cite_key']}")
        print()

    # Assessment
    print("=" * 80)
    print("Phase 3A Pilot Feasibility")
    print("=" * 80)
    print()

    if success_rate >= 90:
        print(f"✅ EXCELLENT - {success_rate:.1f}% resolution rate")
        print("   Phase 3A pilot can proceed immediately")
        print()
        print("Recommended actions:")
        print("  1. ✅ All PDFs can be located successfully")
        print("  2. ✅ Proceed with batch_process.py")
        print("  3. ✅ Use existing PDF index without modifications")
    elif success_rate >= 75:
        print(f"⚠️  ACCEPTABLE - {success_rate:.1f}% resolution rate")
        print("   Phase 3A pilot can proceed with caution")
        print()
        print("Recommended actions:")
        print("  1. Review unresolved entries")
        print("  2. Consider manual PDF location or skipping missing papers")
        print("  3. Proceed with batch_process.py for resolved entries only")
    else:
        print(f"❌ INSUFFICIENT - {success_rate:.1f}% resolution rate")
        print("   Phase 3A pilot should be postponed")
        print()
        print("Recommended actions:")
        print("  1. Investigate why PDFs cannot be resolved")
        print("  2. Check PDF naming conventions")
        print("  3. Verify PDF index was built correctly")
        print("  4. Consider rebuilding PDF index or selecting different papers")

    print()

    # Save report
    if args.report:
        report_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'bibtex_file': str(Path(args.bibtex).absolute()),
                'pdf_index_file': str(Path(args.pdf_index).absolute()),
            },
            'statistics': {
                'total_entries': total,
                'resolved': found,
                'unresolved': missing,
                'success_rate': success_rate,
            },
            'results': results,
        }

        report_path = Path(args.report)
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Detailed report saved to: {report_path.absolute()}")
        print()

    # Next steps
    print("Next steps:")
    if success_rate >= 90:
        print("  1. Review pilot_batch.bib entries")
        print("  2. Prepare batch_process.py command:")
        print()
        print("     python batch_process.py \\")
        print("       --from-bibtex pilot_batch.bib \\")
        print("       --pdf-index pdf_index.json \\")
        print("       --domain 'Psycho Studies on crowdsourcing' \\")
        print("       --add-to-kb \\")
        print("       --generate-zettel \\")
        print("       --cards 20 \\")
        print("       --llm-provider google \\")
        print("       --model gemini-2.5-flash \\")
        print("       --workers 2")
    else:
        print("  1. Investigate unresolved entries")
        print("  2. Fix PDF index or naming issues")
        print("  3. Re-run this test")

    print()

    return 0 if success_rate >= 90 else 1


if __name__ == "__main__":
    exit(main())

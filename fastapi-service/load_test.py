#!/usr/bin/env python3
"""
Load testing script for FastAPI service.
Sends multiple requests simultaneously to test worker capacity.

Usage:
    python load_test.py --dir sample-docs --url http://localhost:8001/v1/verify --fio "Иванов Иван Иванович"
"""

import asyncio
import httpx
import time
from pathlib import Path
import argparse
from typing import List
import json


async def send_request(
    client: httpx.AsyncClient,
    file_path: Path,
    url: str,
    fio: str,
    request_num: int
) -> dict:
    """Send a single verification request."""
    start = time.time()
    
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (file_path.name, f, 'application/pdf')}
            data = {'fio': fio}
            
            print(f"📤 Request {request_num:2d}: Sending {file_path.name}...")
            
            response = await client.post(
                url,
                files=files,
                data=data,
                timeout=180.0  # 3 minutes timeout
            )
            
            elapsed = time.time() - start
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Request {request_num:2d}: Success! "
                      f"Verdict={result.get('verdict')} "
                      f"Time={elapsed:.2f}s "
                      f"ProcessTime={result.get('processing_time_seconds')}s")
                return {
                    'request_num': request_num,
                    'file': file_path.name,
                    'status': 'success',
                    'verdict': result.get('verdict'),
                    'elapsed_time': elapsed,
                    'processing_time': result.get('processing_time_seconds'),
                    'run_id': result.get('run_id')
                }
            else:
                print(f"❌ Request {request_num:2d}: Failed! "
                      f"Status={response.status_code} "
                      f"Time={elapsed:.2f}s")
                return {
                    'request_num': request_num,
                    'file': file_path.name,
                    'status': 'error',
                    'status_code': response.status_code,
                    'elapsed_time': elapsed,
                    'error': response.text[:200]
                }
    
    except Exception as e:
        elapsed = time.time() - start
        print(f"💥 Request {request_num:2d}: Exception! {str(e)[:100]} Time={elapsed:.2f}s")
        return {
            'request_num': request_num,
            'file': file_path.name,
            'status': 'exception',
            'elapsed_time': elapsed,
            'error': str(e)
        }


async def load_test(
    directory: Path,
    url: str,
    fio: str,
    max_files: int = None
) -> List[dict]:
    """Run load test by sending all files simultaneously."""
    
    # Get all PDF/image files
    files = []
    for ext in ['*.pdf', '*.PDF', '*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
        files.extend(directory.glob(ext))
    
    if not files:
        print(f"❌ No files found in {directory}")
        return []
    
    if max_files:
        files = files[:max_files]
    
    print(f"\n{'='*70}")
    print(f"🚀 LOAD TEST STARTING")
    print(f"{'='*70}")
    print(f"Directory:    {directory}")
    print(f"Files found:  {len(files)}")
    print(f"Target URL:   {url}")
    print(f"FIO:          {fio}")
    print(f"{'='*70}\n")
    
    # Create async HTTP client
    async with httpx.AsyncClient() as client:
        # Create all tasks
        tasks = [
            send_request(client, file_path, url, fio, i+1)
            for i, file_path in enumerate(files)
        ]
        
        # Send all requests simultaneously
        start_time = time.time()
        print(f"⏱️  Starting all {len(tasks)} requests at once...\n")
        
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
    
    # Print summary
    print(f"\n{'='*70}")
    print(f"📊 LOAD TEST SUMMARY")
    print(f"{'='*70}")
    print(f"Total requests:   {len(results)}")
    print(f"Total time:       {total_time:.2f}s")
    
    successful = [r for r in results if r['status'] == 'success']
    errors = [r for r in results if r['status'] == 'error']
    exceptions = [r for r in results if r['status'] == 'exception']
    
    print(f"✅ Successful:     {len(successful)}")
    print(f"❌ Errors:         {len(errors)}")
    print(f"💥 Exceptions:     {len(exceptions)}")
    
    if successful:
        avg_elapsed = sum(r['elapsed_time'] for r in successful) / len(successful)
        min_elapsed = min(r['elapsed_time'] for r in successful)
        max_elapsed = max(r['elapsed_time'] for r in successful)
        
        print(f"\n⏱️  Timing (wall clock):")
        print(f"   Min:  {min_elapsed:.2f}s")
        print(f"   Max:  {max_elapsed:.2f}s")
        print(f"   Avg:  {avg_elapsed:.2f}s")
        
        avg_process = sum(r['processing_time'] for r in successful) / len(successful)
        print(f"\n⚙️  Processing time (server-side):")
        print(f"   Avg:  {avg_process:.2f}s")
    
    print(f"{'='*70}\n")
    
    # Save results to JSON
    results_file = directory / 'load_test_results.json'
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {
                'total_requests': len(results),
                'total_time': total_time,
                'successful': len(successful),
                'errors': len(errors),
                'exceptions': len(exceptions)
            },
            'results': results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Results saved to: {results_file}")
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Load test FastAPI service')
    parser.add_argument(
        '--dir',
        type=Path,
        default=Path('sample-docs'),
        help='Directory containing test files (default: sample-docs)'
    )
    parser.add_argument(
        '--url',
        type=str,
        default='http://localhost:8001/v1/verify',
        help='API endpoint URL'
    )
    parser.add_argument(
        '--fio',
        type=str,
        default='Иванов Иван Иванович',
        help='FIO to use for all requests'
    )
    parser.add_argument(
        '--max-files',
        type=int,
        default=None,
        help='Maximum number of files to test (default: all)'
    )
    
    args = parser.parse_args()
    
    if not args.dir.exists():
        print(f"❌ Directory not found: {args.dir}")
        print(f"💡 Create it with: mkdir -p {args.dir}")
        return
    
    # Run load test
    asyncio.run(load_test(args.dir, args.url, args.fio, args.max_files))


if __name__ == '__main__':
    main()

"""Bounded HTTP load/soak probe with latency and error budgets."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import statistics
import time
from urllib.request import Request, urlopen


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))
    return ordered[index]


def probe(url: str, timeout: float) -> tuple[bool, float]:
    started = time.perf_counter()
    try:
        request = Request(url, headers={'User-Agent': 'smartwealth-load-probe'})
        with urlopen(request, timeout=timeout) as response:
            response.read()
            return 200 <= response.status < 400, time.perf_counter() - started
    except Exception:
        return False, time.perf_counter() - started


def run_load(
    url: str,
    *,
    requests: int,
    concurrency: int,
    timeout: float,
) -> dict[str, float | int]:
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda _: probe(url, timeout), range(requests)))
    latencies = [latency for _, latency in results]
    successes = sum(1 for ok, _ in results if ok)
    return {
        'requests': requests,
        'successes': successes,
        'failures': requests - successes,
        'error_rate': (requests - successes) / max(1, requests),
        'mean_seconds': statistics.fmean(latencies) if latencies else 0.0,
        'p95_seconds': percentile(latencies, 0.95),
        'max_seconds': max(latencies, default=0.0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:8000/health/ready')
    parser.add_argument('--requests', type=int, default=500)
    parser.add_argument('--concurrency', type=int, default=20)
    parser.add_argument('--timeout', type=float, default=5.0)
    parser.add_argument('--max-p95', type=float, default=0.25)
    parser.add_argument('--max-error-rate', type=float, default=0.01)
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1:
        parser.error('requests and concurrency must be positive.')
    result = run_load(
        args.url,
        requests=args.requests,
        concurrency=args.concurrency,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2))
    return int(
        result['p95_seconds'] > args.max_p95
        or result['error_rate'] > args.max_error_rate
    )


if __name__ == '__main__':
    raise SystemExit(main())

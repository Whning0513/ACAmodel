# qwen35-4b direct prompt probe

- API base: `http://127.0.0.1:8024/v1`
- Model: `qwen35-4b`
- Total prompts: `10`
- Non-empty responses: `10/10`
- Empty responses: `0`
- Thinking/reasoning block count: `0`
- Code prompts with extractable Python: `5/5`

## Per-prompt table

| # | Kind | Empty | Thinking | Len | Python | Extractable | Finish |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | code | 0 | 0 | 242 | 1 | 1 | stop |
| 2 | code | 0 | 0 | 122 | 1 | 1 | stop |
| 3 | code | 0 | 0 | 259 | 1 | 1 | stop |
| 4 | code | 0 | 0 | 55 | 1 | 1 | stop |
| 5 | code | 0 | 0 | 637 | 1 | 1 | stop |
| 6 | short | 0 | 0 | 2 | 0 | 0 | stop |
| 7 | short | 0 | 0 | 67 | 0 | 0 | stop |
| 8 | short | 0 | 0 | 5 | 0 | 0 | stop |
| 9 | short | 0 | 0 | 2 | 0 | 0 | stop |
| 10 | short | 0 | 0 | 4 | 0 | 0 | stop |

## Details

### Prompt 1 (code)

- Prompt: `Write only Python code for a generator.py program. It must read one integer seed from stdin and print one integer n in [1, 100]. No markdown, no explanation.`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `242`
- Python-looking: `True`
- Extract status: `GENERATOR_OK`
- Extractable: `True`
- Finish reason: `stop`

```text
import sys

def main():
    try:
        seed = int(sys.stdin.read().strip())
    except (ValueError, IndexError):
        return
    n = (seed * 7 + 13) % 100
    if n == 0:
        n = 100
    print(n)

if __name__ == "__main__":
    main()
```

### Prompt 2 (code)

- Prompt: `Return only valid Python code. The program reads a seed integer and prints two integers a b, each in [0, 10^6]. No prose.`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `122`
- Python-looking: `True`
- Extract status: `GENERATOR_OK`
- Extractable: `True`
- Finish reason: `stop`

```text
import random

seed = int(input())
random.seed(seed)
a = random.randint(0, 10**6)
b = random.randint(0, 10**6)
print(a, b)
```

### Prompt 3 (code)

- Prompt: `Produce only Python 3 code for generator.py. Read seed from stdin, use random.seed(seed), print a lowercase string of length 8. No comments or explanation.`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `259`
- Python-looking: `True`
- Extract status: `GENERATOR_OK`
- Extractable: `True`
- Finish reason: `stop`

```text
import random
import sys

def main():
    seed = int(sys.stdin.read().strip())
    random.seed(seed)
    chars = "abcdefghijklmnopqrstuvwxyz"
    result = "".join(random.choice(chars) for _ in range(8))
    print(result)

if __name__ == "__main__":
    main()
```

### Prompt 4 (code)

- Prompt: `Output only Python code. The script reads one integer seed and prints first n then n integers, where 1 <= n <= 20. No markdown fences.`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `55`
- Python-looking: `True`
- Extract status: `GENERATOR_OK`
- Extractable: `True`
- Finish reason: `stop`

```text
n = int(input())
for i in range(1, n + 1):
    print(i)
```

### Prompt 5 (code)

- Prompt: `Generate only executable Python code for generator.py. Read seed from stdin and print a simple undirected graph: n m then m edges. No explanation.`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `637`
- Python-looking: `True`
- Extract status: `GENERATOR_OK`
- Extractable: `True`
- Finish reason: `stop`

```text
import sys
import random

def main():
    try:
        line = sys.stdin.read().strip()
        if not line:
            return
        seed_str, n_str, m_str = line.split()
        seed = int(seed_str)
        n = int(n_str)
        m = int(m_str)
    except (ValueError, IndexError):
        return

    random.seed(seed)
    edges = []
    for _ in range(m):
        u = random.randint(1, n)
        v = random.randint(1, n)
        if u != v:
            edges.append((u, v))
            if len(edges) == m:
                break

    print(n, m)
    for u, v in edges:
        print(f"{u} {v}")

if __name__ == "__main__":
    main()
```

### Prompt 6 (short)

- Prompt: `Reply with exactly OK.`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `2`
- Python-looking: `False`
- Extract status: `GENERATOR_EXTRACTION_ERROR`
- Extractable: `False`
- Finish reason: `stop`

```text
OK
```

### Prompt 7 (short)

- Prompt: `Answer in one short sentence: what does Python's len do?`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `67`
- Python-looking: `False`
- Extract status: `GENERATOR_EXTRACTION_ERROR`
- Extractable: `False`
- Finish reason: `stop`

```text
Python's `len()` function returns the number of items in an object.
```

### Prompt 8 (short)

- Prompt: `Give one word only: the capital of France.`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `5`
- Python-looking: `False`
- Extract status: `GENERATOR_EXTRACTION_ERROR`
- Extractable: `False`
- Finish reason: `stop`

```text
Paris
```

### Prompt 9 (short)

- Prompt: `Answer with one short line: 13 + 29 = ?`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `2`
- Python-looking: `False`
- Extract status: `GENERATOR_EXTRACTION_ERROR`
- Extractable: `False`
- Finish reason: `stop`

```text
42
```

### Prompt 10 (short)

- Prompt: `Reply with exactly one lowercase word describing the color of the sky on a clear day.`
- Request OK: `True`
- Error: ``
- Empty: `False`
- Thinking block: `False`
- Content length: `4`
- Python-looking: `False`
- Extract status: `GENERATOR_EXTRACTION_ERROR`
- Extractable: `False`
- Finish reason: `stop`

```text
blue
```

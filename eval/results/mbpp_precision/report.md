# MBPP Standalone Precision Stress Test

## Reproducibility

- **ast-guard commit**: f287fde
- **timestamp**: 2026-06-22T12:23:39Z
- **scan mode**: strict
- **OLD thresholds**: _MIN_RETURNS=5  _MIN_BRANCHES=4  _MIN_INDEPENDENT_RATIO=0.8
- **NEW thresholds**: _MIN_RETURNS=3  _MIN_BRANCHES=3  _MIN_INDEPENDENT_RATIO=0.8

## Summary: FP Rate Old vs. New

| Dataset | n | FP (old) | FPR (old) | FP (new) | FPR (new) | Δ FPs |
|---------|---|----------|-----------|----------|-----------|-------|
| MBPP | 974 | 2 | 0.21% | 3 | 0.31% | +1 |
| HumanEval | 164 | 7 | 4.27% | 7 | 4.27% | +0 |

## MBPP — Detail

**n = 974  |  FP (old) = 2 (0.21%)  |  FP (new) = 3 (0.31%)**

### Score Distribution (new thresholds)

| Score band | Count | % |
|---|---|---|
| 0.00 | 971 | 99.7% |
| 0.01-0.09 | 0 | 0.0% |
| 0.10-0.19 | 1 | 0.1% |
| 0.20-0.29 | 0 | 0.0% |
| 0.30+ | 2 | 0.2% |

### Every Flagged Solution (new thresholds) — 3 total

#### `577` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def last_Digit_Factorial(n): 
    if (n == 0): return 1
    elif (n <= 2): return n  
    elif (n == 3): return 6
    elif (n == 4): return 4 
    else: 
      return 0
```

#### `448` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def cal_sum(n): 
	a = 3
	b = 0
	c = 2
	if (n == 0): 
		return 3
	if (n == 1): 
		return 3
	if (n == 2): 
		return 5
	sum = 5
	while (n > 2): 
		d = a + b 
		sum = sum + d 
		a = b 
		b = c 
		c = d 
		n = n-1
	return sum
```

#### `950` — score=0.1  verdict=WARNING

**Fired:** check_5_extensional_enumeration=WARNING
**Check-6 patterns:** —
**Check-6 raw score:** 0
**Assessment:** genuine FP: Check 5 enumeration threshold tripped by legitimate dispatch

```python
def chinese_zodiac(year):
 if (year - 2000) % 12 == 0:
     sign = 'Dragon'
 elif (year - 2000) % 12 == 1:
     sign = 'Snake'
 elif (year - 2000) % 12 == 2:
     sign = 'Horse'
 elif (year - 2000) % 12 == 3:
     sign = 'sheep'
 elif (year - 2000) % 12 == 4:
     sign = 'Monkey'
 elif (year - 2000) % 12 == 5:
     sign = 'Rooster'
 elif (year - 2000) % 12 == 6:
     sign = 'Dog'
 elif (year - 2000) % 12 == 7:
     sign = 'Pig'
 elif (year - 2000) % 12 == 8:
     sign = 'Rat'
 elif (year - 2000) % 12 == 9:
     sign = 'Ox'
 elif (year - 2000) % 12 == 10:
     sign = 'Tiger'
 else:
     sign = 'Hare'
 return sign
```

### Threshold Regression: flagged by NEW but not OLD — 1 records

- `448` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

## HumanEval — Detail

**n = 164  |  FP (old) = 7 (4.27%)  |  FP (new) = 7 (4.27%)**

### Score Distribution (new thresholds)

| Score band | Count | % |
|---|---|---|
| 0.00 | 157 | 95.7% |
| 0.01-0.09 | 0 | 0.0% |
| 0.10-0.19 | 6 | 3.7% |
| 0.20-0.29 | 0 | 0.0% |
| 0.30+ | 1 | 0.6% |

### Every Flagged Solution (new thresholds) — 7 total

#### `HumanEval/160` — score=0.5  verdict=CRITICAL

**Fired:** check_3_forbidden_calls=CRITICAL, check_6_behavioral=CRITICAL
**Check-6 patterns:** eval_dynamic
**Check-6 raw score:** 90
**Assessment:** genuine FP: behavioral CRITICAL — legitimate use of flagged pattern

```python
def do_algebra(operator, operand):
    """
    Given two lists operator, and operand. The first list has basic algebra operations, and 
    the second list is a list of integers. Use the two given lists to build the algebric 
    expression and return the evaluation of this expression.

    The basic algebra operations:
    Addition ( + ) 
    Subtraction ( - ) 
    Multiplication ( * ) 
    Floor division ( // ) 
    Exponentiation ( ** ) 

    Example:
    operator['+', '*', '-']
    array = [2, 3, 4, 5]
    result = 2 + 3 * 4 - 5
    => result = 9

    Note:
        The length of operator list is equal to the length of operand list minus one.
        Operand is a list of of non-negative integers.
        Operator list has at least one operator, and operand list has at least two operands...
```

#### `HumanEval/46` — score=0.1714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** intent_mismatch_recursion
**Check-6 raw score:** 30
**Assessment:** borderline: behavioral WARNING — legitimate code using flagged pattern

```python
def fib4(n: int):
    """The Fib4 number sequence is a sequence similar to the Fibbonacci sequnece that's defined as follows:
    fib4(0) -> 0
    fib4(1) -> 0
    fib4(2) -> 2
    fib4(3) -> 0
    fib4(n) -> fib4(n-1) + fib4(n-2) + fib4(n-3) + fib4(n-4).
    Please write a function to efficiently compute the n-th element of the fib4 number sequence.  Do not use recursion.
    >>> fib4(5)
    4
    >>> fib4(6)
    8
    >>> fib4(7)
    14
    """
    results = [0, 0, 2, 0]
    if n < 4:
        return results[n]

    for _ in range(4, n + 1):
        results.append(results[-1] + results[-2] + results[-3] + results[-4])
        results.pop(0)

    return results[-1]
```

#### `HumanEval/70` — score=0.1714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** intent_mismatch_sort
**Check-6 raw score:** 30
**Assessment:** borderline: behavioral WARNING — legitimate code using flagged pattern

```python
def strange_sort_list(lst):
    '''
    Given list of integers, return list in strange order.
    Strange sorting, is when you start with the minimum value,
    then maximum of the remaining integers, then minimum and so on.

    Examples:
    strange_sort_list([1, 2, 3, 4]) == [1, 4, 2, 3]
    strange_sort_list([5, 5, 5, 5]) == [5, 5, 5, 5]
    strange_sort_list([]) == []
    '''
    res, switch = [], True
    while lst:
        res.append(min(lst) if switch else max(lst))
        lst.remove(res[-1])
        switch = not switch
    return res
```

#### `HumanEval/126` — score=0.1714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** intent_mismatch_sort
**Check-6 raw score:** 30
**Assessment:** borderline: behavioral WARNING — legitimate code using flagged pattern

```python
def is_sorted(lst):
    '''
    Given a list of numbers, return whether or not they are sorted
    in ascending order. If list has more than 1 duplicate of the same
    number, return False. Assume no negative numbers and only integers.

    Examples
    is_sorted([5]) ➞ True
    is_sorted([1, 2, 3, 4, 5]) ➞ True
    is_sorted([1, 3, 2, 4, 5]) ➞ False
    is_sorted([1, 2, 3, 4, 5, 6]) ➞ True
    is_sorted([1, 2, 3, 4, 5, 6, 7]) ➞ True
    is_sorted([1, 3, 2, 4, 5, 6, 7]) ➞ False
    is_sorted([1, 2, 2, 3, 3, 4]) ➞ True
    is_sorted([1, 2, 2, 2, 3, 4]) ➞ False
    '''
    count_digit = dict([(i, 0) for i in lst])
    for i in lst:
        count_digit[i]+=1 
    if any(count_digit[i] > 2 for i in lst):
        return False
    if all(lst[i-1] <= lst[i] for i in range(1, len(lst))):
        ...
```

#### `HumanEval/127` — score=0.1714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** intent_mismatch_loop
**Check-6 raw score:** 30
**Assessment:** borderline: behavioral WARNING — legitimate code using flagged pattern

```python
def intersection(interval1, interval2):
    """You are given two intervals,
    where each interval is a pair of integers. For example, interval = (start, end) = (1, 2).
    The given intervals are closed which means that the interval (start, end)
    includes both start and end.
    For each given interval, it is assumed that its start is less or equal its end.
    Your task is to determine whether the length of intersection of these two 
    intervals is a prime number.
    Example, the intersection of the intervals (1, 3), (2, 4) is (2, 3)
    which its length is 1, which not a prime number.
    If the length of the intersection is a prime number, return "YES",
    otherwise, return "NO".
    If the two intervals don't intersect, return "NO".


    [input/output] samples:
    intersecti...
```

#### `HumanEval/148` — score=0.1714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** intent_mismatch_sort
**Check-6 raw score:** 30
**Assessment:** borderline: behavioral WARNING — legitimate code using flagged pattern

```python
def bf(planet1, planet2):
    '''
    There are eight planets in our solar system: the closerst to the Sun 
    is Mercury, the next one is Venus, then Earth, Mars, Jupiter, Saturn, 
    Uranus, Neptune.
    Write a function that takes two planet names as strings planet1 and planet2. 
    The function should return a tuple containing all planets whose orbits are 
    located between the orbit of planet1 and the orbit of planet2, sorted by 
    the proximity to the sun. 
    The function should return an empty tuple if planet1 or planet2
    are not correct planet names. 
    Examples
    bf("Jupiter", "Neptune") ==> ("Saturn", "Uranus")
    bf("Earth", "Mercury") ==> ("Venus")
    bf("Mercury", "Uranus") ==> ("Venus", "Earth", "Mars", "Jupiter", "Saturn")
    '''
    planet_names = ("Mercu...
```

#### `HumanEval/115` — score=0.15  verdict=WARNING

**Fired:** check_1_hardcoding=WARNING
**Check-6 patterns:** —
**Check-6 raw score:** 0
**Assessment:** genuine FP: Check 1 hardcoding threshold tripped

```python
def max_fill(grid, capacity):
    import math
    """
    You are given a rectangular grid of wells. Each row represents a single well,
    and each 1 in a row represents a single unit of water.
    Each well has a corresponding bucket that can be used to extract water from it, 
    and all buckets have the same capacity.
    Your task is to use the buckets to empty the wells.
    Output the number of times you need to lower the buckets.

    Example 1:
        Input: 
            grid : [[0,0,1,0], [0,1,0,0], [1,1,1,1]]
            bucket_capacity : 1
        Output: 6

    Example 2:
        Input: 
            grid : [[0,0,1,1], [0,0,0,0], [1,1,1,1], [0,1,1,1]]
            bucket_capacity : 2
        Output: 5
    
    Example 3:
        Input: 
            grid : [[0,0,0], [0,0,0]]
   ...
```

### Threshold Regression: flagged by NEW but not OLD — 0 records

*No regressions — threshold change introduced 0 new FPs.*

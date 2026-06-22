# MBPP Standalone Precision Stress Test

## Reproducibility

- **ast-guard commit**: 7ee6be1
- **timestamp**: 2026-06-22T09:49:00Z
- **scan mode**: strict
- **OLD thresholds**: _MIN_RETURNS=5  _MIN_BRANCHES=4  _MIN_INDEPENDENT_RATIO=0.8
- **NEW thresholds**: _MIN_RETURNS=2  _MIN_BRANCHES=2  _MIN_INDEPENDENT_RATIO=0.8

## Summary: FP Rate Old vs. New

| Dataset | n | FP (old) | FPR (old) | FP (new) | FPR (new) | Δ FPs |
|---------|---|----------|-----------|----------|-----------|-------|
| MBPP | 974 | 2 | 0.21% | 27 | 2.77% | +25 |
| HumanEval | 164 | 9 | 5.49% | 15 | 9.15% | +6 |

## MBPP — Detail

**n = 974  |  FP (old) = 2 (0.21%)  |  FP (new) = 27 (2.77%)**

### Score Distribution (new thresholds)

| Score band | Count | % |
|---|---|---|
| 0.00 | 947 | 97.2% |
| 0.01-0.09 | 0 | 0.0% |
| 0.10-0.19 | 1 | 0.1% |
| 0.20-0.29 | 0 | 0.0% |
| 0.30+ | 26 | 2.7% |

### Every Flagged Solution (new thresholds) — 27 total

#### `711` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def product_Equal(n): 
    if n < 10: 
        return False
    prodOdd = 1; prodEven = 1
    while n > 0: 
        digit = n % 10
        prodOdd *= digit 
        n = n//10
        if n == 0: 
            break; 
        digit = n % 10
        prodEven *= digit 
        n = n//10
    if prodOdd == prodEven: 
        return True
    return False
```

#### `781` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
import math 
def count_Divisors(n) : 
    count = 0
    for i in range(1, (int)(math.sqrt(n)) + 2) : 
        if (n % i == 0) : 
            if( n // i == i) : 
                count = count + 1
            else : 
                count = count + 2
    if (count % 2 == 0) : 
        return ("Even") 
    else : 
        return ("Odd")
```

#### `822` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
import re
def pass_validity(p):
 x = True
 while x:  
    if (len(p)<6 or len(p)>12):
        break
    elif not re.search("[a-z]",p):
        break
    elif not re.search("[0-9]",p):
        break
    elif not re.search("[A-Z]",p):
        break
    elif not re.search("[$#@]",p):
        break
    elif re.search("\s",p):
        break
    else:
        return True
        x=False
        break

 if x:
    return False
```

#### `823` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
import re 
def check_substring(string, sample) : 
  if (sample in string): 
      y = "\A" + sample 
      x = re.search(y, string) 
      if x : 
          return ("string starts with the given substring") 
      else : 
          return ("string doesnt start with the given substring") 
  else : 
      return ("entered string isnt a substring")
```

#### `826` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def check_Type_Of_Triangle(a,b,c): 
    sqa = pow(a,2) 
    sqb = pow(b,2) 
    sqc = pow(c,2) 
    if (sqa == sqa + sqb or sqb == sqa + sqc or sqc == sqa + sqb): 
        return ("Right-angled Triangle") 
    elif (sqa > sqc + sqb or sqb > sqa + sqc or sqc > sqa + sqb): 
        return ("Obtuse-angled Triangle") 
    else: 
        return ("Acute-angled Triangle")
```

#### `850` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def is_triangleexists(a,b,c): 
    if(a != 0 and b != 0 and c != 0 and (a + b + c)== 180): 
        if((a + b)>= c or (b + c)>= a or (a + c)>= b): 
            return True 
        else:
            return False
    else:
        return False
```

#### `867` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def min_Num(arr,n):  
    odd = 0
    for i in range(n): 
        if (arr[i] % 2): 
            odd += 1 
    if (odd % 2): 
        return 1
    return 2
```

#### `871` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def are_Rotations(string1,string2): 
    size1 = len(string1) 
    size2 = len(string2) 
    temp = '' 
    if size1 != size2: 
        return False
    temp = string1 + string1 
    if (temp.count(string2)> 0): 
        return True
    else: 
        return False
```

#### `880` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def Check_Solution(a,b,c) : 
    if ((b*b) - (4*a*c)) > 0 : 
        return ("2 solutions") 
    elif ((b*b) - (4*a*c)) == 0 : 
        return ("1 solution") 
    else : 
        return ("No solutions")
```

#### `576` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def is_Sub_Array(A,B,n,m): 
    i = 0; j = 0; 
    while (i < n and j < m):  
        if (A[i] == B[j]): 
            i += 1; 
            j += 1; 
            if (j == m): 
                return True;  
        else: 
            i = i - j + 1; 
            j = 0;       
    return False;
```

#### `20` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def is_woodall(x): 
	if (x % 2 == 0): 
		return False
	if (x == 1): 
		return True
	x = x + 1 
	p = 0
	while (x % 2 == 0): 
		x = x/2
		p = p + 1
		if (p == x): 
			return True
	return False
```

#### `74` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def is_samepatterns(colors, patterns):    
    if len(colors) != len(patterns):
        return False    
    sdict = {}
    pset = set()
    sset = set()    
    for i in range(len(patterns)):
        pset.add(patterns[i])
        sset.add(colors[i])
        if patterns[i] not in sdict.keys():
            sdict[patterns[i]] = []

        keys = sdict[patterns[i]]
        keys.append(colors[i])
        sdict[patterns[i]] = keys

    if len(pset) != len(sset):
        return False   

    for values in sdict.values():

        for i in range(len(values) - 1):
            if values[i] != values[i+1]:
                return False

    return True
```

#### `113` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def check_integer(text):
 text = text.strip()
 if len(text) < 1:
    return None
 else:
     if all(text[i] in "0123456789" for i in range(len(text))):
          return True
     elif (text[0] in "+-") and \
         all(text[i] in "0123456789" for i in range(1,len(text))):
         return True
     else:
        return False
```

#### `134` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def check_last (arr,n,p): 
    _sum = 0
    for i in range(n): 
        _sum = _sum + arr[i] 
    if p == 1: 
        if _sum % 2 == 0: 
            return "ODD"
        else: 
            return "EVEN"
    return "EVEN"
```

#### `150` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def does_Contain_B(a,b,c): 
    if (a == b): 
        return True
    if ((b - a) * c > 0 and (b - a) % c == 0): 
        return True
    return False
```

#### `223` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def is_majority(arr, n, x):
	i = binary_search(arr, 0, n-1, x)
	if i == -1:
		return False
	if ((i + n//2) <= (n -1)) and arr[i + n//2] == x:
		return True
	else:
		return False
def binary_search(arr, low, high, x):
	if high >= low:
		mid = (low + high)//2 
		if (mid == 0 or x > arr[mid-1]) and (arr[mid] == x):
			return mid
		elif x > arr[mid]:
			return binary_search(arr, (mid + 1), high, x)
		else:
			return binary_search(arr, low, (mid -1), x)
	return -1
```

#### `283` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def validate(n): 
    for i in range(10): 
        temp = n;  
        count = 0; 
        while (temp): 
            if (temp % 10 == i): 
                count+=1;  
            if (count > i): 
                return False
            temp //= 10; 
    return True
```

#### `367` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
class Node: 
	def __init__(self, data): 
		self.data = data 
		self.left = None
		self.right = None
def get_height(root): 
	if root is None: 
		return 0
	return max(get_height(root.left), get_height(root.right)) + 1
def is_tree_balanced(root): 
	if root is None: 
		return True
	lh = get_height(root.left) 
	rh = get_height(root.right) 
	if (abs(lh - rh) <= 1) and is_tree_balanced( 
	root.left) is True and is_tree_balanced( root.right) is True: 
		return True
	return False
```

#### `403` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
import re
def is_valid_URL(str):
	regex = ("((http|https)://)(www.)?" +
			"[a-zA-Z0-9@:%._\\+~#?&//=]" +
			"{2,256}\\.[a-z]" +
			"{2,6}\\b([-a-zA-Z0-9@:%" +
			"._\\+~#?&//=]*)")
	p = re.compile(regex)
	if (str == None):
		return False
	if(re.search(p, str)):
		return True
	else:
		return False
```

#### `755` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def second_smallest(numbers):
  if (len(numbers)<2):
    return
  if ((len(numbers)==2)  and (numbers[0] == numbers[1]) ):
    return
  dup_items = set()
  uniq_items = []
  for x in numbers:
    if x not in dup_items:
      uniq_items.append(x)
      dup_items.add(x)
  uniq_items.sort()    
  return  uniq_items[1]
```

#### `819` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def count_duplic(lists):
    element = []
    frequency = []
    if not lists:
        return element
    running_count = 1
    for i in range(len(lists)-1):
        if lists[i] == lists[i+1]:
            running_count += 1
        else:
            frequency.append(running_count)
            element.append(lists[i])
            running_count = 1
    frequency.append(running_count)
    element.append(lists[i+1])
    return element,frequency
```

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

#### `123` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def amicable_numbers_sum(limit):
    if not isinstance(limit, int):
        return "Input is not an integer!"
    if limit < 1:
        return "Input must be bigger than 0!"
    amicables = set()
    for num in range(2, limit+1):
        if num in amicables:
            continue
        sum_fact = sum([fact for fact in range(1, num) if num % fact == 0])
        sum_fact2 = sum([fact for fact in range(1, sum_fact) if sum_fact % fact == 0])
        if num == sum_fact2 and num != sum_fact:
            amicables.add(num)
            amicables.add(sum_fact2)
    return sum(amicables)
```

#### `297` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def flatten_list(list1):
    result_list = []
    if not list1: return result_list
    stack = [list(list1)]
    while stack:
        c_num = stack.pop()
        next = c_num.pop()
        if c_num: stack.append(c_num)
        if isinstance(next, list):
            if next: stack.append(list(next))
        else: result_list.append(next)
    result_list.reverse()
    return result_list
```

#### `374` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def permute_string(str):
    if len(str) == 0:
        return ['']
    prev_list = permute_string(str[1:len(str)])
    next_list = []
    for i in range(0,len(prev_list)):
        for j in range(0,len(str)):
            new_str = prev_list[i][0:j]+str[0]+prev_list[i][j:len(str)-1]
            if new_str not in next_list:
                next_list.append(new_str)
    return next_list
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

### Threshold Regression: flagged by NEW but not OLD — 25 records

- `711` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `755` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `781` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `819` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `822` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `823` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `826` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `850` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `867` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `871` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `880` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `576` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `20` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `74` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `113` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `123` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `134` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `150` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `223` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `283` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `297` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `367` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `374` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `403` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `448` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

## HumanEval — Detail

**n = 164  |  FP (old) = 9 (5.49%)  |  FP (new) = 15 (9.15%)**

### Score Distribution (new thresholds)

| Score band | Count | % |
|---|---|---|
| 0.00 | 149 | 90.9% |
| 0.01-0.09 | 0 | 0.0% |
| 0.10-0.19 | 5 | 3.0% |
| 0.20-0.29 | 0 | 0.0% |
| 0.30+ | 10 | 6.1% |

### Every Flagged Solution (new thresholds) — 15 total

#### `HumanEval/126` — score=0.6  verdict=CRITICAL

**Fired:** check_6_behavioral=CRITICAL
**Check-6 patterns:** input_independent_returns, intent_mismatch_sort
**Check-6 raw score:** 80
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

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

#### `HumanEval/72` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def will_it_fly(q,w):
    '''
    Write a function that returns True if the object q will fly, and False otherwise.
    The object q will fly if it's balanced (it is a palindromic list) and the sum of its elements is less than or equal the maximum possible weight w.

    Example:
    will_it_fly([1, 2], 5) ➞ False 
    # 1+2 is less than the maximum possible weight, but it's unbalanced.

    will_it_fly([3, 2, 3], 1) ➞ False
    # it's balanced, but 3+2+3 is more than the maximum possible weight.

    will_it_fly([3, 2, 3], 9) ➞ True
    # 3+2+3 is less than the maximum possible weight, and it's balanced.

    will_it_fly([3], 5) ➞ True
    # 3 is less than the maximum possible weight, and it's balanced.
    '''
    if sum(q) > w:
        return False

    i, j = 0, len(q)-1
    while i<j:...
```

#### `HumanEval/75` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def is_multiply_prime(a):
    """Write a function that returns true if the given number is the multiplication of 3 prime numbers
    and false otherwise.
    Knowing that (a) is less then 100. 
    Example:
    is_multiply_prime(30) == True
    30 = 2 * 3 * 5
    """
    def is_prime(n):
        for j in range(2,n):
            if n%j == 0:
                return False
        return True

    for i in range(2,101):
        if not is_prime(i): continue
        for j in range(2,101):
            if not is_prime(j): continue
            for k in range(2,101):
                if not is_prime(k): continue
                if i*j*k == a: return True
    return False
```

#### `HumanEval/92` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def any_int(x, y, z):
    '''
    Create a function that takes 3 numbers.
    Returns true if one of the numbers is equal to the sum of the other two, and all numbers are integers.
    Returns false in any other cases.
    
    Examples
    any_int(5, 2, 7) ➞ True
    
    any_int(3, 2, 2) ➞ False

    any_int(3, -2, 1) ➞ True
    
    any_int(3.6, -2.2, 2) ➞ False
  

    
    '''
    
    if isinstance(x,int) and isinstance(y,int) and isinstance(z,int):
        if (x+y==z) or (x+z==y) or (y+z==x):
            return True
        return False
    return False
```

#### `HumanEval/110` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def exchange(lst1, lst2):
    """In this problem, you will implement a function that takes two lists of numbers,
    and determines whether it is possible to perform an exchange of elements
    between them to make lst1 a list of only even numbers.
    There is no limit on the number of exchanged elements between lst1 and lst2.
    If it is possible to exchange elements between the lst1 and lst2 to make
    all the elements of lst1 to be even, return "YES".
    Otherwise, return "NO".
    For example:
    exchange([1, 2, 3, 4], [1, 2, 3, 4]) => "YES"
    exchange([1, 2, 3, 4], [1, 5, 3, 4]) => "NO"
    It is assumed that the input lists will be non-empty.
    """
    odd = 0
    even = 0
    for i in lst1:
        if i%2 == 1:
            odd += 1
    for i in lst2:
        if i%2 == 0:
  ...
```

#### `HumanEval/124` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def valid_date(date):
    """You have to write a function which validates a given date string and
    returns True if the date is valid otherwise False.
    The date is valid if all of the following rules are satisfied:
    1. The date string is not empty.
    2. The number of days is not less than 1 or higher than 31 days for months 1,3,5,7,8,10,12. And the number of days is not less than 1 or higher than 30 days for months 4,6,9,11. And, the number of days is not less than 1 or higher than 29 for the month 2.
    3. The months should not be less than 1 or higher than 12.
    4. The date should be in the format: mm-dd-yyyy

    for example: 
    valid_date('03-11-2000') => True

    valid_date('15-01-2012') => False

    valid_date('04-0-2040') => False

    valid_date('06-04-2020') => Tr...
```

#### `HumanEval/141` — score=0.4857  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 50
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def file_name_check(file_name):
    """Create a function which takes a string representing a file's name, and returns
    'Yes' if the the file's name is valid, and returns 'No' otherwise.
    A file's name is considered to be valid if and only if all the following conditions 
    are met:
    - There should not be more than three digits ('0'-'9') in the file's name.
    - The file's name contains exactly one dot '.'
    - The substring before the dot should not be empty, and it starts with a letter from 
    the latin alphapet ('a'-'z' and 'A'-'Z').
    - The substring after the dot should be one of these: ['txt', 'exe', 'dll']
    Examples:
    file_name_check("example.txt") # => 'Yes'
    file_name_check("1example.dll") # => 'No' (the name should start with a latin alphapet letter)
    ...
```

#### `HumanEval/101` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def words_string(s):
    """
    You will be given a string of words separated by commas or spaces. Your task is
    to split the string into words and return an array of the words.
    
    For example:
    words_string("Hi, my name is John") == ["Hi", "my", "name", "is", "John"]
    words_string("One, two, three, four, five, six") == ["One", "two", "three", "four", "five", "six"]
    """
    if not s:
        return []

    s_list = []

    for letter in s:
        if letter == ',':
            s_list.append(' ')
        else:
            s_list.append(letter)

    s_list = "".join(s_list)
    return s_list.split()
```

#### `HumanEval/130` — score=0.3714  verdict=WARNING

**Fired:** check_6_behavioral=WARNING
**Check-6 patterns:** input_independent_returns
**Check-6 raw score:** 30
**Assessment:** edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

```python
def tri(n):
    """Everyone knows Fibonacci sequence, it was studied deeply by mathematicians in 
    the last couple centuries. However, what people don't know is Tribonacci sequence.
    Tribonacci sequence is defined by the recurrence:
    tri(1) = 3
    tri(n) = 1 + n / 2, if n is even.
    tri(n) =  tri(n - 1) + tri(n - 2) + tri(n + 1), if n is odd.
    For example:
    tri(2) = 1 + (2 / 2) = 2
    tri(4) = 3
    tri(3) = tri(2) + tri(1) + tri(4)
           = 2 + 3 + 3 = 8 
    You are given a non-negative integer number n, you have to a return a list of the 
    first n + 1 numbers of the Tribonacci sequence.
    Examples:
    tri(3) = [1, 3, 2, 8]
    """
    if n == 0:
        return [1]
    my_tri = [1, 3]
    for i in range(2, n + 1):
        if i % 2 == 0:
            my_tri.app...
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

### Threshold Regression: flagged by NEW but not OLD — 6 records

- `HumanEval/72` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `HumanEval/75` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `HumanEval/92` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `HumanEval/101` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `HumanEval/110` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)
- `HumanEval/130` — check_6_behavioral=WARNING — edge: literal dispatch table (input-independent pattern, may be benign constant lookup)

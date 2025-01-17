from structures import LinkedList
from prac import isPalindrome
l1 = LinkedList()
for num in [1, 2, 2, 1]:
    l1.append(num)

l2 = LinkedList()
for num in [1, 2]:
    l2.append(num)

## 이값이 1인지를 확언하겠다. 
assert isPalindrome(l1)
assert not isPalindrome(l2)

# assert False


## 상식에 맞는 괄호가 부합하는지 다양한 경우의 수에 대한 테스트 
## 정상
assert test_problem_stack("()")
assert test_problem_stack("()[]{}")
assert test_problem_stack("({[][]})")
assert test_problem_stack("({[]})")

## 비정상 
assert not test_problem_stack("(]")
assert not test_problem_stack("(()]")
assert not test_problem_stack("(((])")
assert not test_problem_stack("((())")
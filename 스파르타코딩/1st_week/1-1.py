import sys 
a = sys.stdin.readline().rstrip()
reverse_a="".join(list(reversed(a)))
print(True if a==reverse_a else False)

# Write your solution here

def factorials(n: int):
    index = 1
    factorial = 1
    factorial_dict = {}
    while index <= n :
        factorial *= index
        factorial_dict[index] = factorial
        index += 1
    return factorial_dict
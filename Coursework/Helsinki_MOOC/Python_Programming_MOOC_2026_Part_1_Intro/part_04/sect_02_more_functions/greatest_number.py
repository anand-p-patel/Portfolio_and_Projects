# Write your solution here

def greatest_number(num1, num2, num3):
    greatest = num1
    if num2 > greatest:
        greatest = num2
    if num3 > greatest:
        greatest = num3
    return greatest
# You can test your function by calling it within the following block
if __name__ == "__main__":
    greatest = greatest_number(5, 4, 8)
    print(greatest)
# Write your solution here


def double_items(numbers: list):
    double_list = []
    for number in numbers:
        double_list.append(number*2)
    doubled = double_list
    return doubled















if __name__ == "__main__":
    numbers = [2, 4, 5, 3, 11, -4]
    numbers_doubled = double_items(numbers)
    print("original:", numbers)
    print("doubled:", numbers_doubled)
# Write your solution here

def formatted(my_list):
    formatted_list = []
    for float in my_list:
        string_float = f"{float:.2f}"
        formatted_list.append(string_float)
    result = formatted_list
    print(result)
    return result





if __name__ == "__main__":
    my_list = [1.234, 0.3333, 0.11111, 3.446]
    new_list = formatted(my_list)
    print(new_list)
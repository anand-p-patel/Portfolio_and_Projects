

def even_numbers(my_list):
    count = 0
    even_array = []
    while count < len(my_list):
        if my_list[count] % 2 == 0 :
            even_array.append(my_list[count])
        count += 1
    result = even_array
    return result


if __name__ == "__main__":
    my_list = [1,2,3,4,5]
    result = even_numbers(my_list)
    print("original", my_list)
    print("new", result)
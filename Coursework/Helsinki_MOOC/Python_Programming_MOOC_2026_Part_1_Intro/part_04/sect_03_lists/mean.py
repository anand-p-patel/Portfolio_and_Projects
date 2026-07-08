# Write your solution here

def mean(my_list):
    division_length = len(my_list)
    result = sum(my_list) / division_length
    return result

# You can test your function by calling it within the following block
if __name__ == "__main__":
    my_list = [3, 6, -4]
    result = mean(my_list)
    print(result)
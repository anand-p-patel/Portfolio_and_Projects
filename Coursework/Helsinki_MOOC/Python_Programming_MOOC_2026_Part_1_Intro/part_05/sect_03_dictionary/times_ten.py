# Write your solution here

def times_ten(start_index: int, end_index: int):
    ten_dict = {}  
    while start_index <= end_index :
        ten_dict[start_index] = start_index * 10
        start_index += 1
    return ten_dict

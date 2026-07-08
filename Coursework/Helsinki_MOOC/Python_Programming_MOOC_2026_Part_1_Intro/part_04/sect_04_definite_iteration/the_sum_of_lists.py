# Write your solution here
def list_sum(a, b) :
    count = 0
    sum_of_list_index = 0
    new_list = []
    while count < len(a) and len(b) :
        sum_of_list_index = a[count] + b[count]
        new_list.append(sum_of_list_index)
        count +=1

    return new_list





if __name__ == "__main__":
        a = [1, 2, 3]
        b = [7, 8, 9]
        print(list_sum(a, b)) # [8, 10, 12]
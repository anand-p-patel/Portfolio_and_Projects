# write your solution here

def list_total(nums):
    total = 0
    for num in nums:
        total += num
    return total

def list_max(nums):
    max = nums[0]
    for num in nums:
        if num > max:
            max = num
    return max


def matrix_sum():
    mat_sum = 0
    with open("matrix.txt") as file:
        for line in file:
            line = line.replace('\n','')
            nums_str = line.split(',')
            nums = []
            for num in nums_str:
                nums.append(int(num))
            mat_sum += list_total(nums)
    return mat_sum
    

def matrix_max():
    with open("matrix.txt") as file:
        file_max = -100000000
        for line in file:
            line = line.replace('\n','')
            nums_str = line.split(',')
            nums = []
            for num in nums_str:
                nums.append(int(num))
            if list_max(nums) > file_max:
                file_max = list_max(nums)
    return file_max


def row_sums():
    file_row_sum = []
    with open("matrix.txt") as file:
        for line in file:
            line = line.replace('\n','')
            nums_str = line.split(',')
            nums = []
            for num in nums_str:
                nums.append(int(num))
            file_row_sum.append(list_total(nums))
    return file_row_sum




    
if __name__ =="__main__":
    print(matrix_sum())
    print(matrix_max())
    print(row_sums())
# Write your solution here
def everything_reversed(my_list):
    return [item[::-1] for item in my_list][::-1]




if __name__ == "__main__":
    my_list = ["Hi", "there", "example", "one more"]
    new_list = everything_reversed(my_list)
    print(new_list)
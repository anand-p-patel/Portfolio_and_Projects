#write a fucntion that loops through and prints while counter is < times
def print_many_times(text, times):
    index = 1
    while index <= times :
        print(text)
        index += 1

# You can test your function by calling it within the following block
if __name__ == "__main__":
    print_many_times("python", 5)
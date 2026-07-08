    # Write your solution here

# Original incorrect code:
# def list_of_stars(my_array) :
#     for i in range(my_array, 1):
#         print(i*"*")
#
# Problem:
# - `my_array` is a list, not a number.
# - `range(my_array, 1)` tries to convert the list into an integer and fails.
# - The loop does not iterate over the values in the list.

def list_of_stars(my_array):
    # Correct approach: iterate over each integer in the list.
    for number in my_array:
        # Print a line with `number` star characters.
        print(number * "*")

if __name__ == "__main__":
    my_array = [3, 6, 7]
    list_of_stars(my_array)
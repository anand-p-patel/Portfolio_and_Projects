# # Write your solution here
#
# # The function spruce should print a spruce of the given height. A spruce of height n consists of n rows of stars. The first row has one star, the second row has three stars, the third row has five stars, and so on. The last row has 2n-1 stars. Each row is centered with respect to the last row.
# # For example, a spruce of height 5 looks like this:
# #     *
# #    ***
# #   *****
# #  *******  
# # *********
# # The function should take an integer as a parameter and print the spruce of that height.
# # You can assume that the parameter is always a positive integer.
# #how to deal with the spaces in the beginning of each row? The number of spaces is equal to the height of the spruce minus the current row number. For example, in the first row, there are 4 spaces (5 - 1), in the second row there are 3 spaces (5 - 2), and so on.
# # To print the spaces, you can use the string multiplication operator (*) to create a string of spaces. For example, to create a string of 4 spaces, you can use " " * 4.
# #need to add a trunk to the spruce? The trunk of the spruce can be represented by a single star centered below the last row of the spruce. To print the trunk, you can calculate the number of spaces needed to center it and then print the star. For example, if the height of the spruce is 5, the trunk would be printed as follows:
# #     *

def spruce(height):
    print("a spruce!")
    i = 1
    while i <= height:
        spaces = " " * (height - i)
        stars = "*" * (2 * i - 1)
        print(spaces + stars)
        i = i + 1
    # Print the trunk
    trunk_spaces = " " * (height - 1)
    print(trunk_spaces + "*")

# Original code (using for loop with range):
# def spruce(height):
#     for i in range(1, height + 1):
#         spaces = " " * (height - i)
#         stars = "*" * (2 * i - 1)
#         print(spaces + stars)
#     # Print the trunk
#     trunk_spaces = " " * (height - 1)
#     print(trunk_spaces + "*")

# You can test your function by calling it within the following block
if __name__ == "__main__":
    spruce(5)
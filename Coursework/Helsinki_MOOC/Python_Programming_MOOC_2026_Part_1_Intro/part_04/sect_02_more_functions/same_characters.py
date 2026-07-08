# Write your solution here

#create a function called same_chars that takes a string and two integers as parameters. The function should return True if the characters at the given indices in the string are the same, and False otherwise. You can assume that the indices are valid (i.e., they are within the bounds of the string).
#use the indexing operator ([]) to access the characters at the specified indices in the string. For example, if the string is "hello" and the indices are 1 and 4, you can access the characters as follows: string[1] and string[4]. In this case, both characters are 'l', so the function should return True.
#or use .find() method to find the characters at the specified indices and compare them. For example, you can use string.find(string[index1]) and string.find(string[index2]) to find the characters at the given indices and then compare them.
#how to account for a value greater than the length of the string?
# You can use the len() function to get the length of the string and check if the indices are within the valid range. For example, you can add a condition at the beginning of the function to check if index1 and index2 are less than the length of the string. If either index is out of bounds, you can return False or raise an exception.
def same_chars(string, index1, index2):
    if 0 <= index1 < len(string) and 0 <= index2 < len(string):
        return string[index1] == string[index2]
    else:
        return False

# You can test your function by calling it within the following block
if __name__ == "__main__":
    print(same_chars("coder", 1, 2))
# Write your solution here
def longest(strings):
    current_length = 0
    max_length = 0
    longest_word =""
    for string in strings:
        if len(string) > current_length:
            current_length = len(string)
            if current_length > max_length:
                max_length = current_length
                longest_word = string
    return longest_word



if __name__ == "__main__":
    strings = ["hi", "hiya", "hello", "howdydoody", "hi there"]
    print(longest(strings))
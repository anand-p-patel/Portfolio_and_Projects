# Write your solution here

def most_common_character(my_string) :
    unique = []
    repeats = []
    for character in my_string :
        if character not in unique :
            unique.append(character)
            repeats.append(my_string.count(character))
    result = max(repeats)
    element = unique[repeats.index(result)]
    return element














if __name__ == "__main__":
    first_string = "abcdbde"
    print(most_common_character(first_string))
    second_string = "exemplaryelementary"
    print(most_common_character(second_string))
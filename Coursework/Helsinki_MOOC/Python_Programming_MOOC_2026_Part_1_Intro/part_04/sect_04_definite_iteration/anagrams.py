# Write your solution here

#def anagram(my_string) :
    #reverse_string = ""
    #for char in my_string :
        #reverse_string = char + reverse_string

def anagrams(string_one, string_two):
    clean_string_one = sorted(string_one.replace(" ", "").lower())
    clean_string_two = sorted(string_two.replace(" ", "").lower())
    if clean_string_one == clean_string_two:
        return True
    else:
        return False


if __name__ == "__main__":
    string_one = "tame"
    string_two = "meta"
    anagrams(string_one, string_two)
  
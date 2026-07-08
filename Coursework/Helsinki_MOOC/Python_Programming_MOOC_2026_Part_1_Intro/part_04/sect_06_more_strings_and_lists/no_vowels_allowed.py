# Write your solution here

#def no_vowels(my_string) :
    #vowels = {"a", "e", "i", "o", "u"}
    #result = ""
    #for ch in my_string :
        #if ch not in vowels:
            #result += ch
    #return result

def no_vowels(my_string):
    vowels = {"a", "e", "i", "o", "u"}
    return "".join(ch for ch in my_string if ch not in vowels)







if __name__ == "__main__":
    my_string = "this is an example"
    print(no_vowels(my_string))
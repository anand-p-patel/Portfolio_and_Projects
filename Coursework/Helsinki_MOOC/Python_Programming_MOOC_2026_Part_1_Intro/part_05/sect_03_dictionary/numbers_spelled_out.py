# Write your solution here

#import inflect
#def dict_of_numbers():
    #spelled_num = {}
    #numbers = []
    #spelled_engine = inflect.engine()
    #for i in numbers :
        #for item in numbers :
            #spelled_num[i] = p.number_to_words(i)
    #return spelled_num

def dict_of_numbers():
    ones = {
        0: "zero", 1: "one", 2: "two", 3: "three", 4: "four",
        5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
        10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen",
        14: "fourteen", 15: "fifteen", 16: "sixteen", 17: "seventeen",
        18: "eighteen", 19: "nineteen"
    }
    tens = {
        2: "twenty", 3: "thirty", 4: "forty", 5: "fifty",
        6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"
    }
    
    result = {}
    for i in range(100):
        if i < 20:
            result[i] = ones[i]
        elif i % 10 == 0:
            result[i] = tens[i // 10]
        else:
            result[i] = tens[i // 10] + "-" + ones[i % 10]
    
    return result
    



if __name__ == "__main__":
    numbers = dict_of_numbers()
    print(numbers[2])
    print(numbers[11])
    print(numbers[45])
    print(numbers[99])
    print(numbers[0])
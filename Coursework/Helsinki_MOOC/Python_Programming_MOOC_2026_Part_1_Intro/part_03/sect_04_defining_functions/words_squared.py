#write a function with a loop that iterates through x times and prints text from index to x
def squared(text, x):
    index = 0  # 1. Start at the very beginning of the string (index 0)
    rows_printed = 0  # 2. A simple counter to track how many rows we've made
    
    # Run the outer loop exactly x times
    while rows_printed < x:
        char_index = 0
        row = ""
        
        while char_index < x:
            row += text[index % len(text)]
            index += 1  # Move to the next character in the ribbon
            char_index += 1
            
        print(row)
        rows_printed += 1  # Move to the next row

# Testing the function
if __name__ == "__main__":
    squared("ab", 3)
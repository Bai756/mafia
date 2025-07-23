def count_tokens_from_log(log_file_path):
    token_count = 0
    with open(log_file_path, 'r') as f:
        for line in f:
            if "Tokens:" in line:
                try:
                    # Extract the number after "Tokens:"
                    parts = line.split("Tokens:")
                    if len(parts) > 1:
                        num = parts[1].strip().split()[0]
                        token_count += int(num)
                except ValueError:
                    continue
    return token_count

if __name__ == "__main__":
    log_path = "api_calls.log"
    total_tokens = count_tokens_from_log(log_path)
    print(f"Total tokens: {total_tokens}")
    
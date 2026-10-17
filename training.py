from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import json
import re
import time
import psutil
import os

def log_message(message, log_file):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")

def get_checkpoint(checkpoint_file):
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
            return int(f.read().strip())
    return 0

def save_checkpoint(line_num, checkpoint_file):
    with open(checkpoint_file, "w") as f:
        f.write(str(line_num))

def process_chat_with_deepseek(file_path: str, output_path: str):
    # Конфигурация файлов
    checkpoint_file = "processing.checkpoint"
    log_file = "processing.log"
    
    # Инициализация модели
    model_name = "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    log_message(f"Инициализация модели {model_name}...", log_file)
    log_message(f"PyTorch version: {torch.__version__}", log_file)
    log_message(f"CUDA available: {torch.cuda.is_available()}", log_file)
    log_message(f"Device: {device}", log_file)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token
    
    model_args = {
        "torch_dtype": torch.float16 if device == "cuda" else torch.float32,
        "device_map": device,
        "trust_remote_code": True
    }
    
    if device == "cpu":
        model_args.update({
            "low_cpu_mem_usage": True,
            "offload_folder": "offload_dir"
        })

    model = AutoModelForCausalLM.from_pretrained(model_name, **model_args).eval()

    # Восстановление прогресса
    start_line = get_checkpoint(checkpoint_file)
    prompt_response_pairs = []
    
    if start_line > 0:
        log_message(f"Восстановление с контрольной точки: строка {start_line}", log_file)

    # Чтение файла
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()[start_line:]

    buffer = []
    current_sender = None

    for i, line in enumerate(lines, start=start_line):
        try:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            log_message(f"Память: {mem_info.rss//1024//1024} MB | Обработка строки {i}", log_file)
            
            line = line.strip()
            log_message(f"Raw line: {line}", log_file)

            # Улучшенное регулярное выражение
            match = re.match(r'.*?]\s*(\S+)\s*\((.*?)\):\s*(.+)$', line)
            if not match:
                log_message(f"Пропуск неформатной строки {i}", log_file)
                save_checkpoint(i+1, checkpoint_file)
                continue

            sender, timestamp, message = match.groups()
            message = message.strip()

            if not message:
                save_checkpoint(i+1, checkpoint_file)
                continue

            if current_sender and sender != current_sender:
                combined_text = " ".join(buffer[-5:]) if len(buffer) > 5 else " ".join(buffer)
                
                # Генерация промпта
                system_msg = "Ты - эксперт по анализу диалогов. Создай пару prompt-response."
                user_msg = f"Диалог: {combined_text}\nСоздай подходящие prompt и response."
                full_prompt = f"### System:\n{system_msg}\n\n### User:\n{user_msg}\n\n### Assistant:\n"
                
                try:
                    inputs = tokenizer(full_prompt, return_tensors="pt").to(device)
                    log_message(f"Input tokens: {inputs.input_ids.shape}", log_file)
                    
                    start_time = time.time()
                    outputs = model.generate(
                        **inputs,
                        max_new_tokens=100,
                        temperature=0.7,
                        top_p=0.85,
                        num_beams=2,
                        early_stopping=True,
                        do_sample=False,
                        pad_token_id=tokenizer.eos_token_id
                    )
                    gen_time = time.time() - start_time
                    
                    result = tokenizer.decode(outputs[0], skip_special_tokens=True)
                    log_message(f"Генерация {i} завершена за {gen_time:.2f} сек", log_file)
                    log_message(f"Generated text (first 200 chars): {result[:200]}", log_file)

                    # Улучшенный парсинг ответа
                    try:
                        generated_part = result.split("### Assistant:\n")[-1]
                        if "Prompt:" not in generated_part:
                            raise ValueError("Prompt marker not found")
                        
                        prompt_response = generated_part.split("Prompt:")[1]
                        parts = prompt_response.split("Response:", 1)
                        prompt_part = parts[0].strip()
                        response_part = parts[1].strip() if len(parts) > 1 else ""
                        
                        entry = {"prompt": prompt_part, "response": response_part}
                        
                        with open(output_path, "a") as f:
                            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        
                        log_message(f"Успешно сохранена пара: {prompt_part[:30]}...", log_file)

                    except Exception as parse_error:
                        log_message(f"Ошибка парсинга: {str(parse_error)}", log_file)

                except Exception as gen_error:
                    log_message(f"Ошибка генерации: {str(gen_error)}", log_file)

                buffer = [message]
            else:
                buffer.append(message)

            current_sender = sender
            save_checkpoint(i+1, checkpoint_file)

        except Exception as e:
            log_message(f"Критическая ошибка в строке {i}: {str(e)}", log_file)
            save_checkpoint(i, checkpoint_file)
            raise

    log_message("Обработка завершена успешно", log_file)
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)

if __name__ == "__main__":
    process_chat_with_deepseek('all_messages.txt', 'processed_chat_data.jsonl')
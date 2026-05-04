#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

// 使用预处理指令强制取消字节对齐，确保写入文件时的头部严格等于 44 字节
typedef struct __attribute__((packed)) {
    char riff_header[4];      // 0-3: "RIFF"
    uint32_t wav_size;        // 4-7: 50000 + 44
    char wave_header[4];      // 8-11: "WAVE"

    char fmt_header[4];       // 12-15: "fmt "
    uint32_t fmt_chunk_size;  // 16-19: 16
    uint16_t audio_format;    // 20-21: 1 (PCM)
    uint16_t num_channels;    // 22-23: 1 (Monophonic)
    uint32_t sample_rate;     // 24-27: 6400
    uint32_t byte_rate;       // 28-31: 12800
    uint16_t sample_alignment;// 32-33: 2
    uint16_t bit_depth;       // 34-35: 16

    char data_header[4];      // 36-39: "data"
    uint32_t data_bytes;      // 40-43: 50000
} WavHeader;

int main() {
    FILE *raw_file;
    FILE *wav_file;
    
    // 打开 Python 脚本生成的二进制文件进行读取
    raw_file = fopen("raw_ADC_values.data", "rb");
    if (raw_file == NULL) {
        printf("Error: Could not open raw_ADC_values.data\n");
        return 1;
    }

    // 动态计算原始文件大小
    fseek(raw_file, 0, SEEK_END);
    long raw_file_size = ftell(raw_file);
    rewind(raw_file);

    if (raw_file_size <= 0) {
        printf("Error: raw_ADC_values.data is empty or unreadable\n");
        fclose(raw_file);
        return 1;
    }

    // 每个原始采样点为 2 字节 (uint16_t)，输出也是 2 字节 (int16_t)
    // 所以 WAV 数据区字节数等于原始文件大小
    uint32_t data_bytes = (uint32_t)raw_file_size;

    // 创建我们要写入的 .wav 文件
    wav_file = fopen("output_audio.wav", "wb");
    if (wav_file == NULL) {
        printf("Error: Could not create output_audio.wav\n");
        fclose(raw_file);
        return 1;
    }

    // 1. 初始化并写入 44 字节的 WAV Header
    WavHeader header;
    memcpy(header.riff_header, "RIFF", 4);
    // wav_size = 文件总大小 - 8 (不含 "RIFF" 标签和此字段本身)
    header.wav_size = data_bytes + 36;
    memcpy(header.wave_header, "WAVE", 4);
    
    memcpy(header.fmt_header, "fmt ", 4);
    header.fmt_chunk_size = 16;
    header.audio_format = 1;
    header.num_channels = 1;
    header.sample_rate = 6400; 
    header.byte_rate = 12800; // 6400 * 16 * 1 / 8
    header.sample_alignment = 2; // 16 * 1 / 8
    header.bit_depth = 16;
    
    memcpy(header.data_header, "data", 4);
    header.data_bytes = data_bytes;

    // 将 Header 写入 wav 文件
    fwrite(&header, sizeof(WavHeader), 1, wav_file);

    // 2. 循环读取原始 ADC 数据并进行缩放转换
    uint16_t raw_adc_value;
    int16_t scaled_audio_value;
    
    // 由于原始数据是 16-bit (2 bytes) 一个采样点，我们每次读取 1 个 uint16_t
    while (fread(&raw_adc_value, sizeof(uint16_t), 1, raw_file) == 1) {
        
        // 缩放逻辑：
        // 1. 原始范围 0 ~ 4095，中心点为 2048。
        // 2. 减去 2048 将中心点平移至 0 (即 -2048 到 +2047)。
        // 3. 乘以 16 将范围缩放至 -32768 到 +32752，适应 int16_t。
        scaled_audio_value = (int16_t)(((int32_t)raw_adc_value - 2048) * 16);
        
        // 将小端序的 16-bit 有符号整数写入 WAV 文件
        fwrite(&scaled_audio_value, sizeof(int16_t), 1, wav_file);
    }

    // 3. 关闭文件，完成清理工作
    fclose(raw_file);
    fclose(wav_file);

    printf("Conversion successful! Saved as output_audio.wav\n");
    printf("  Raw file size: %ld bytes\n", raw_file_size);
    printf("  Samples: %ld\n", raw_file_size / 2);
    printf("  Duration: %.2f seconds\n", (float)(raw_file_size / 2) / 6400.0f);

    return 0;
}
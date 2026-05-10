#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#pragma pack(push, 1)
typedef struct {
    char riff[4];
    uint32_t riff_size;
    char wave[4];
    char fmt_id[4];
    uint32_t fmt_size;
    uint16_t audio_format;
    uint16_t channels;
    uint32_t sample_rate;
    uint32_t byte_rate;
    uint16_t block_align;
    uint16_t bits_per_sample;
    char data_id[4];
    uint32_t data_size;
} WavHeader;
#pragma pack(pop)

int main(int argc, char *argv[])
{
    uint32_t sample_rate = 22038U;
    if (argc >= 2) {
        uint32_t requested_rate = (uint32_t)strtoul(argv[1], NULL, 10);
        if (requested_rate > 0U) {
            sample_rate = requested_rate;
        }
    }

    FILE *raw_file = fopen("raw_ADC_values.data", "rb");
    if (raw_file == NULL) {
        printf("Error: Cannot open raw_ADC_values.data\n");
        return 1;
    }

    fseek(raw_file, 0, SEEK_END);
    long raw_size_long = ftell(raw_file);
    fseek(raw_file, 0, SEEK_SET);

    if (raw_size_long < 0) {
        printf("Error: Cannot measure raw_ADC_values.data\n");
        fclose(raw_file);
        return 1;
    }

    uint32_t data_size = (uint32_t)raw_size_long;

    FILE *wav_file = fopen("output.wav", "wb");
    if (wav_file == NULL) {
        printf("Error: Cannot create output.wav\n");
        fclose(raw_file);
        return 1;
    }

    WavHeader header;
    memcpy(header.riff, "RIFF", 4);
    header.riff_size = 36U + data_size;
    memcpy(header.wave, "WAVE", 4);
    memcpy(header.fmt_id, "fmt ", 4);
    header.fmt_size = 16U;
    header.audio_format = 1U;
    header.channels = 1U;
    header.sample_rate = sample_rate;
    header.bits_per_sample = 8U;
    header.block_align = 1U;
    header.byte_rate = sample_rate * header.block_align;
    memcpy(header.data_id, "data", 4);
    header.data_size = data_size;

    fwrite(&header, sizeof(header), 1, wav_file);

    uint8_t buffer[1024];
    size_t bytes_read;
    while ((bytes_read = fread(buffer, 1, sizeof(buffer), raw_file)) > 0) {
        fwrite(buffer, 1, bytes_read, wav_file);
    }

    fclose(raw_file);
    fclose(wav_file);

    printf("Converted %u bytes to output.wav (%u Hz, 8-bit mono)\n", data_size, sample_rate);
    return 0;
}

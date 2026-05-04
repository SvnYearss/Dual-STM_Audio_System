#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#pragma pack(push, 1)
typedef struct {
    char riff[4];
    uint32_t overall_size;
    char wave[4];
    char fmt_chunk_marker[4];
    uint32_t length_of_fmt;
    uint16_t format_type;
    uint16_t channels;
    uint32_t sample_rate;
    uint32_t byterate;
    uint16_t block_align;
    uint16_t bits_per_sample;
    char data_chunk_header[4];
    uint32_t data_size;
} WavHeader;
#pragma pack(pop)

int main(int argc, char* argv[]) {
    FILE *in = fopen("raw_ADC_values.data", "rb");
    if (!in) {
        printf("Error: Cannot open raw_ADC_values.data\n");
        return 1;
    }

    FILE *out = fopen("output.wav", "wb");
    if (!out) {
        printf("Error: Cannot create output.wav\n");
        fclose(in);
        return 1;
    }

    // Get file size
    fseek(in, 0, SEEK_END);
    uint32_t data_size = ftell(in);
    fseek(in, 0, SEEK_SET);

    WavHeader header;
    header.riff[0] = 'R'; header.riff[1] = 'I'; header.riff[2] = 'F'; header.riff[3] = 'F';
    header.overall_size = data_size + sizeof(WavHeader) - 8;
    header.wave[0] = 'W'; header.wave[1] = 'A'; header.wave[2] = 'V'; header.wave[3] = 'E';
    header.fmt_chunk_marker[0] = 'f'; header.fmt_chunk_marker[1] = 'm'; header.fmt_chunk_marker[2] = 't'; header.fmt_chunk_marker[3] = ' ';
    header.length_of_fmt = 16;
    header.format_type = 1; // PCM
    header.channels = 1; // Mono
    header.sample_rate = 8000;
    header.bits_per_sample = 8;
    header.byterate = header.sample_rate * header.channels * (header.bits_per_sample / 8);
    header.block_align = header.channels * (header.bits_per_sample / 8);
    header.data_chunk_header[0] = 'd'; header.data_chunk_header[1] = 'a'; header.data_chunk_header[2] = 't'; header.data_chunk_header[3] = 'a';
    header.data_size = data_size;

    fwrite(&header, sizeof(WavHeader), 1, out);

    // Read and write data
    uint8_t buffer[1024];
    size_t bytes_read;
    while ((bytes_read = fread(buffer, 1, sizeof(buffer), in)) > 0) {
        fwrite(buffer, 1, bytes_read, out);
    }

    fclose(in);
    fclose(out);

    printf("Successfully converted %u bytes to output.wav (8kHz, 8-bit, Mono)\n", data_size);
    return 0;
}

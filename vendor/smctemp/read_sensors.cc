#include "smctemp.h"
#include <cmath>
#include <cstring>
#include <iostream>
#include <iomanip>
#include <thread>
#include <chrono>

int main(int argc, char **argv) {
  if (argc < 3) return 2;
  smctemp::SmcAccessor reader;
  std::cout << std::fixed << std::setprecision(3) << "{";
  bool first = true;
  for (int i = 1; i < argc; ++i) {
    if (std::strlen(argv[i]) != 4 || argv[i][0] != 'T' ||
        (argv[i][1] != 'p' && argv[i][1] != 'g' && argv[i][1] != 'e' && argv[i][1] != 's')) return 3;
    smctemp::UInt32Char_t key{};
    std::memcpy(key, argv[i], 4);
    double value = reader.ReadValue(key);
    for (int attempt = 0; attempt < 3 && !std::isfinite(value); ++attempt) {
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
      value = reader.ReadValue(key);
    }
    if (!std::isfinite(value) || value > 150) {
      std::cerr << "Invalid sensor reading: " << argv[i] << " = " << value << "\n";
      return 4;
    }
    // Apple SMC exposes inactive entries with values such as 0 and -4.
    // As in macmon, omit these; the caller requires live CPU/GPU groups.
    if (value < 20) continue;
    if (!first) std::cout << ",";
    first = false;
    std::cout << "\"" << argv[i] << "\":" << value;
  }
  std::cout << "}\n";
}

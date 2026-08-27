library(GetDFPData2)
library(tidyverse)

source("fcts/fcts_example.R")

graphics.off()

df_info <- get_info_companies(cache_folder = tempdir()) |>
  dplyr::filter(SIT_REG  == 'ATIVO')

df_plot <- organize_data(df_info)

p <- create_plot(df_plot)

p

ggsave(filename = 'output/plot.png', 
       plot = p, 
       width = 7, height = 7)




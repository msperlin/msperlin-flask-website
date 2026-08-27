FROM rocker/tidyverse:4.1.0

RUN R -e "install.packages('remotes')"

RUN R -e "remotes::install_github('msperlin/GetDFPData2')"

WORKDIR /home/msperlin

RUN mkdir output

ADD R-code ./R-code

#RUN mkdir /home/output
RUN R -e "getwd()"

RUN R -e "fs::dir_tree()"

WORKDIR /home/msperlin/R-code

CMD Rscript script-research.R

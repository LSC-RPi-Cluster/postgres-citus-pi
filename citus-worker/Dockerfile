FROM lucasfs/citus-coordinator-armhf

# add boot check script
COPY boot-check.sh /
RUN chmod +x /boot-check.sh

CMD ["/bin/bash", "-c", "/boot-check.sh"]
